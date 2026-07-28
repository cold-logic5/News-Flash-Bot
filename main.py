import os
import re
import json
import asyncio
import logging
import aiohttp
import feedparser
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Load environment variables from .env file
load_dotenv()

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
ACCOUNTS_STR = os.getenv("ACCOUNTS", "sunnewstamil,News18TamilNadu,polimernews,NewsTamilTV24x7")
ACCOUNTS = [acc.strip() for acc in ACCOUNTS_STR.split(",") if acc.strip()]

CACHE_FILE = "posted_tweets.json"

# Working RSS / Nitter mirrors with fallback support
RSS_INSTANCES = [
    "https://nitter.net",
    "https://xcancel.com",
    "https://nitter.poast.org",
]

def load_posted_urls() -> set:
    """Load cached tweet IDs from local JSON file."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            logging.error(f"Error reading cache file: {e}")
    return set()

def save_posted_urls(posted_urls: set):
    """Save seen tweet IDs to local JSON file, keeping max 50 items."""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(list(posted_urls)[-50:], f, indent=2)
    except Exception as e:
        logging.error(f"Error saving cache file: {e}")

async def fetch_working_feed(session: aiohttp.ClientSession, account: str):
    """Asynchronously fetch RSS feed trying mirrors until a valid feed is returned."""
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
                    
                    if feed.entries and "whitelisted" not in title.lower():
                        logging.info(f"Successfully fetched feed for @{account} from {instance}")
                        return feed
        except Exception as e:
            logging.debug(f"Error fetching from {instance} for @{account}: {e}")
            
    logging.warning(f"Could not fetch valid RSS feed for @{account} from any instance.")
    return None

async def send_discord_webhook(session: aiohttp.ClientSession, webhook_url: str, message_content: str) -> bool:
    """Send HTTP POST request to Discord Webhook URL."""
    payload = {"content": message_content}
    try:
        async with session.post(webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status in (200, 204):
                logging.info("Successfully posted to Discord Webhook.")
                return True
            else:
                body = await response.text()
                logging.error(f"Discord Webhook returned status {response.status}: {body}")
                return False
    except Exception as e:
        logging.error(f"Error posting to Discord Webhook: {e}")
        return False

async def main():
    if not WEBHOOK_URL or WEBHOOK_URL == "YOUR_DISCORD_WEBHOOK_URL_HERE":
        logging.error("DISCORD_WEBHOOK_URL environment variable is missing or invalid.")
        return

    posted_urls = load_posted_urls()
    is_first_run = len(posted_urls) == 0

    async with aiohttp.ClientSession() as session:
        for account in ACCOUNTS:
            feed = await fetch_working_feed(session, account)
            if not feed or not feed.entries:
                continue
            
            # On first run, process only the single newest tweet per account
            entries_to_check = [feed.entries[0]] if is_first_run else reversed(feed.entries)
            
            for entry in entries_to_check:
                raw_link = getattr(entry, "link", "")
                
                # Extract numeric Tweet Status ID (/status/123456789)
                match = re.search(r"/status/(\d+)", raw_link)
                if not match:
                    continue
                
                tweet_id = match.group(1)
                unique_key = f"{account}_{tweet_id}"
                
                if unique_key in posted_urls:
                    continue
                
                posted_urls.add(unique_key)
                
                # Format URL using fxtwitter for rich Discord media embeds
                fxtwitter_url = f"https://fxtwitter.com/{account}/status/{tweet_id}"
                message = f"📰 **New update from @{account}**\n{fxtwitter_url}"
                
                success = await send_discord_webhook(session, WEBHOOK_URL, message)
                if success:
                    await asyncio.sleep(1.5)  # Rate limit protection
            
            await asyncio.sleep(2)  # Delay between account processing

    save_posted_urls(posted_urls)
    logging.info("RSS Feed Monitor execution finished successfully.")

if __name__ == "__main__":
    asyncio.run(main())
