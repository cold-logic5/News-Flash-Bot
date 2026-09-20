import os
import re
import sys
import json
import time
import calendar
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
ACCOUNTS_STR = os.getenv("ACCOUNTS", "sunnewstamil,News18TamilNadu,polimernews")
ACCOUNTS = [acc.strip() for acc in ACCOUNTS_STR.split(",") if acc.strip()]

CACHE_FILE = "posted_tweets.json"
MAX_CACHE_SIZE = 500  # Store up to 500 recent IDs to avoid re-posting
MAX_AGE_SECONDS = 3 * 3600  # Ignore tweets older than 3 hours

# Working RSS / Nitter mirrors with fallback support
RSS_INSTANCES = [
    "https://nitter.perennialte.ch",
    "https://nitter.privacyredirect.com",
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
    """Save seen tweet IDs to local JSON file, keeping max MAX_CACHE_SIZE items deterministically sorted."""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            sorted_urls = sorted(list(posted_urls))
            json.dump(sorted_urls[-MAX_CACHE_SIZE:], f, indent=2)
    except Exception as e:
        logging.error(f"Error saving cache file: {e}")

async def fetch_tweets_for_account(
    session: aiohttp.ClientSession,
    account: str,
    posted_urls: set,
    is_first_run: bool,
    now: float
) -> list:
    """Fetch recent tweets for an account using direct X.com HTML scraping with Nitter RSS as fallback."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    # Strategy 1: Direct X.com / Twitter.com scraping
    for domain in ["https://x.com", "https://twitter.com"]:
        url = f"{domain}/{account}"
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as response:
                if response.status == 200:
                    html = await response.text()
                    pattern = rf"/{account}/status/(\d+)"
                    matches = list(dict.fromkeys(re.findall(pattern, html, re.IGNORECASE)))
                    if matches:
                        candidates = [matches[0]] if is_first_run else matches
                        found = []
                        for tweet_id in candidates:
                            unique_key = f"{account}_{tweet_id}"
                            if unique_key in posted_urls:
                                continue
                            try:
                                # Twitter Snowflake ID encodes UTC timestamp in milliseconds
                                published_ts = ((int(tweet_id) >> 22) + 1288834974657) / 1000.0
                            except ValueError:
                                continue
                            if not is_first_run and (now - published_ts > MAX_AGE_SECONDS):
                                continue
                            found.append({
                                "account": account,
                                "tweet_id": tweet_id,
                                "unique_key": unique_key,
                                "published_ts": published_ts
                            })
                        logging.info(f"Successfully scraped {len(found)} candidate tweets for @{account} from {domain}")
                        return found
        except Exception as e:
            logging.debug(f"Direct scrape from {domain} for @{account} failed: {e}")

    # Strategy 2: Nitter RSS fallback
    for instance in RSS_INSTANCES:
        feed_url = f"{instance}/{account}/rss"
        try:
            async with session.get(feed_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    content = await response.text()
                    feed = await asyncio.to_thread(feedparser.parse, content)
                    title = str(feed.feed.get("title", ""))
                    if feed.entries and "whitelisted" not in title.lower():
                        entries_to_inspect = [feed.entries[0]] if is_first_run else feed.entries
                        found = []
                        for entry in entries_to_inspect:
                            raw_link = getattr(entry, "link", "")
                            match = re.search(r"/status/(\d+)", raw_link)
                            if not match:
                                continue
                            tweet_id = match.group(1)
                            unique_key = f"{account}_{tweet_id}"
                            if unique_key in posted_urls:
                                continue
                            published_parsed = entry.get("published_parsed")
                            published_ts = calendar.timegm(published_parsed) if published_parsed else now
                            if not is_first_run and (now - published_ts > MAX_AGE_SECONDS):
                                continue
                            found.append({
                                "account": account,
                                "tweet_id": tweet_id,
                                "unique_key": unique_key,
                                "published_ts": published_ts
                            })
                        logging.info(f"Successfully fetched {len(found)} candidate tweets for @{account} from {instance}")
                        return found
        except Exception as e:
            logging.debug(f"RSS mirror {instance} failed for @{account}: {e}")

    logging.warning(f"Could not fetch valid tweets for @{account} from any source.")
    return []

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
        sys.exit(1)

    posted_urls = load_posted_urls()
    is_first_run = len(posted_urls) == 0
    now = time.time()

    all_unposted_tweets = []

    async with aiohttp.ClientSession() as session:
        # Step 1: FETCH (In parallel using asyncio.gather)
        tasks = [fetch_tweets_for_account(session, account, posted_urls, is_first_run, now) for account in ACCOUNTS]
        results = await asyncio.gather(*tasks)

        for account_tweets in results:
            all_unposted_tweets.extend(account_tweets)

        if not all_unposted_tweets:
            logging.info("No new tweets to post.")
            return

        # Step 2: Sort ALL unposted tweets across all accounts chronologically (oldest first)
        all_unposted_tweets.sort(key=lambda item: item["published_ts"])

        logging.info(f"Found {len(all_unposted_tweets)} new tweets across all accounts. Posting in chronological order...")

        # Step 3: Post tweets to Discord in exact chronological sequence
        newly_posted = 0
        for tweet_info in all_unposted_tweets:
            account = tweet_info["account"]
            tweet_id = tweet_info["tweet_id"]
            unique_key = tweet_info["unique_key"]

            fxtwitter_url = f"https://fxtwitter.com/{account}/status/{tweet_id}"
            message = f"📰 **New update from @{account}**\n{fxtwitter_url}"
            
            success = await send_discord_webhook(session, WEBHOOK_URL, message)
            if success:
                posted_urls.add(unique_key)
                newly_posted += 1
                await asyncio.sleep(1.5)  # Rate limit protection between webhooks

    if newly_posted > 0:
        save_posted_urls(posted_urls)
    logging.info("RSS Feed Monitor execution finished successfully.")

if __name__ == "__main__":
    asyncio.run(main())
