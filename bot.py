import os
import re
import json
import asyncio
import logging
import aiohttp
import feedparser
import discord
from discord.ext import tasks, commands
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Load environment variables from .env file
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "10"))
ACCOUNTS_STR = os.getenv("ACCOUNTS", "sunnewstamil,News18TamilNadu")
ACCOUNTS = [acc.strip() for acc in ACCOUNTS_STR.split(",") if acc.strip()]

CACHE_FILE = "posted_tweets.json"

# List of working Nitter / RSS instances to query (with automatic fallback)
RSS_INSTANCES = [
    "https://nitter.net",
    "https://xcancel.com",
    "https://nitter.poast.org",
]

def load_posted_urls() -> set:
    """Load cached tweet IDs/URLs from local JSON file to prevent duplicate posts."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            logging.error(f"Error reading cache file: {e}")
    return set()

def save_posted_urls(posted_urls: set):
    """Save seen tweet IDs/URLs to local JSON file, keeping only the last 50 entries."""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(list(posted_urls)[-50:], f, indent=2)
    except Exception as e:
        logging.error(f"Error saving cache file: {e}")



posted_urls = load_posted_urls()
is_first_run = len(posted_urls) == 0

# Initialize Discord Bot
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

async def fetch_working_feed(session: aiohttp.ClientSession, account: str):
    """Fetch RSS feed by trying working instances in order until valid entries are found."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*"
    }
    
    for instance in RSS_INSTANCES:
        feed_url = f"{instance}/{account}/rss"
        try:
            async with session.get(feed_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    content = await response.text()
                    feed = await asyncio.to_thread(feedparser.parse, content)
                    title = str(feed.feed.get("title", ""))
                    
                    # Verify feed is valid and not a block/whitelist error page
                    if feed.entries and "whitelisted" not in title.lower():
                        logging.info(f"Successfully fetched feed for @{account} from {instance}")
                        return feed
                else:
                    logging.debug(f"HTTP {response.status} from {instance} for @{account}")
        except Exception as e:
            logging.debug(f"Error fetching from {instance} for @{account}: {e}")
            
    logging.warning(f"Could not fetch valid RSS feed for @{account} from any instance.")
    return None

@tasks.loop(minutes=INTERVAL_MINUTES)
async def check_rss_feeds():
    global is_first_run, posted_urls
    
    if not CHANNEL_ID:
        logging.error("CHANNEL_ID is not configured in environment variables.")
        return

    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        try:
            channel = await bot.fetch_channel(CHANNEL_ID)
        except Exception as e:
            logging.error(f"Could not fetch specified Discord channel (ID: {CHANNEL_ID}): {e}")
            return

    async with aiohttp.ClientSession() as session:
        for account in ACCOUNTS:
            feed = await fetch_working_feed(session, account)
            
            if not feed or not feed.entries:
                continue
            
            # On first run, post only the single latest tweet per account
            entries_to_check = [feed.entries[0]] if is_first_run else reversed(feed.entries)
            
            for entry in entries_to_check:
                raw_link = getattr(entry, "link", "")
                
                # Extract the numeric Tweet Status ID (e.g. /status/1234567890)
                match = re.search(r"/status/(\d+)", raw_link)
                if not match:
                    # Skip invalid links (e.g. error page or channel homepage links)
                    continue
                
                tweet_id = match.group(1)
                unique_key = f"{account}_{tweet_id}"
                
                if unique_key in posted_urls:
                    continue
                
                posted_urls.add(unique_key)
                
                # Construct FixTweet URL so Discord renders rich media embed (video, images, text)
                fxtwitter_url = f"https://fxtwitter.com/{account}/status/{tweet_id}"
                message = f"📰 **New update from @{account}**\n{fxtwitter_url}"
                
                try:
                    await channel.send(message)
                    logging.info(f"Posted update for @{account}: {fxtwitter_url}")
                    await asyncio.sleep(1.5)  # Rate limit protection
                except Exception as e:
                    logging.error(f"Failed to send Discord message: {e}")
            
            await asyncio.sleep(2)  # Delay between accounts

    save_posted_urls(posted_urls)

    if is_first_run:
        logging.info("First run complete. Posted initial tweets. Listening for new updates...")
        is_first_run = False

async def start_health_check_server():
    """Start a lightweight HTTP server to satisfy Render Web Service port scanning."""
    port = os.getenv("PORT")
    if not port:
        return
    
    app = aiohttp.web.Application()
    app.router.add_get("/", lambda req: aiohttp.web.Response(text="Bot is running!"))
    app.router.add_get("/health", lambda req: aiohttp.web.Response(text="OK"))
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "0.0.0.0", int(port))
    await site.start()
    logging.info(f"Health check HTTP server started on port {port}")

@bot.event
async def on_ready():
    logging.info(f"Logged in securely as {bot.user.name} (ID: {bot.user.id})")
    await start_health_check_server()
    if not check_rss_feeds.is_running():
        check_rss_feeds.start()

if __name__ == "__main__":
    if not TOKEN or TOKEN == "YOUR_DISCORD_TOKEN_HERE":
        logging.error("Please set a valid DISCORD_TOKEN in your .env file.")
    else:
        bot.run(TOKEN)

