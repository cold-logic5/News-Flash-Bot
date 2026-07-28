import os
import re
import json
import time
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
MAX_CACHE_SIZE = 500  # Store up to 500 recent IDs to avoid re-posting
MAX_AGE_SECONDS = 3 * 3600  # Ignore tweets older than 3 hours

# Working RSS / Nitter mirrors with fallback support
RSS_INSTANCES = [
    "https://nitter.net",
    "https://nitter.poast.org",
    "https://xcancel.com",
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
    """Save seen tweet IDs to local JSON file, keeping max MAX_CACHE_SIZE items."""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(list(posted_urls)[-MAX_CACHE_SIZE:], f, indent=2)
    except Exception as e:
        logging.error(f"Error saving cache file: {e}")

async def fetch_working_feed(session: aiohttp.ClientSession, account: str):
    """Asynchronously fetch RSS feed trying mirrors until a valid feed is returned."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
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
    now = time.time()

    all_unposted_tweets = []

    async with aiohttp.ClientSession() as session:
        # Step 1: Collect unposted tweets across ALL accounts into a single pool
        for account in ACCOUNTS:
            feed = await fetch_working_feed(session, account)
            if not feed or not feed.entries:
                continue
            
            # If first run ever, only consider the newest tweet for each account
            entries_to_inspect = [feed.entries[0]] if is_first_run else feed.entries
            
            for entry in entries_to_inspect:
                raw_link = getattr(entry, "link", "")
                
                # Extract numeric Tweet Status ID (/status/123456789)
                match = re.search(r"/status/(\d+)", raw_link)
                if not match:
                    continue
                
                tweet_id = match.group(1)
                unique_key = f"{account}_{tweet_id}"
                
                if unique_key in posted_urls:
                    continue

                # Parse published timestamp
                published_parsed = entry.get("published_parsed")
                published_ts = time.mktime(published_parsed) if published_parsed else now

                # Skip tweets older than MAX_AGE_SECONDS (e.g. 3 hours) except on initial first run
                if not is_first_run and (now - published_ts > MAX_AGE_SECONDS):
                    logging.info(f"Skipping older tweet {unique_key} (published > 3h ago)")
                    continue

                all_unposted_tweets.append({
                    "account": account,
                    "tweet_id": tweet_id,
                    "unique_key": unique_key,
                    "published_ts": published_ts
                })
            
            await asyncio.sleep(1)  # Brief delay between account fetches

        if not all_unposted_tweets:
            logging.info("No new tweets to post.")
            save_posted_urls(posted_urls)
            return

        # Step 2: Sort ALL unposted tweets across all accounts chronologically (oldest first)
        all_unposted_tweets.sort(key=lambda item: item["published_ts"])

        logging.info(f"Found {len(all_unposted_tweets)} new tweets across all accounts. Posting in chronological order...")

        # Step 3: Post tweets to Discord in exact chronological sequence
        for tweet_info in all_unposted_tweets:
            account = tweet_info["account"]
            tweet_id = tweet_info["tweet_id"]
            unique_key = tweet_info["unique_key"]

            fxtwitter_url = f"https://fxtwitter.com/{account}/status/{tweet_id}"
            message = f"📰 **New update from @{account}**\n{fxtwitter_url}"
            
            success = await send_discord_webhook(session, WEBHOOK_URL, message)
            if success:
                posted_urls.add(unique_key)
                await asyncio.sleep(1.5)  # Rate limit protection between webhooks

    save_posted_urls(posted_urls)
    logging.info("RSS Feed Monitor execution finished successfully.")

if __name__ == "__main__":
    asyncio.run(main())
