import os
import re
import sys
import json
import time
import calendar
import asyncio
import logging
import base64
from typing import Optional, Set, Tuple
import aiohttp
from aiohttp import web
import feedparser
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Load environment variables from .env file
load_dotenv()

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
ACCOUNTS_STR = os.getenv("ACCOUNTS", "sunnewstamil,News18TamilNadu,polimernews")
ACCOUNTS = [acc.strip() for acc in ACCOUNTS_STR.split(",") if acc.strip()]

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO", "cold-logic5/News-Flash-Bot")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "master")

PORT = os.getenv("PORT")
CRON_SECRET = os.getenv("CRON_SECRET")

# Concurrency lock to prevent simultaneous overlapping runs
run_lock = asyncio.Lock()

CACHE_FILE = "posted_tweets.json"
MAX_CACHE_SIZE = 500  # Store up to 500 recent IDs to avoid re-posting
MAX_AGE_SECONDS = 3 * 3600  # Ignore tweets older than 3 hours

# Working RSS / Nitter mirrors with fallback support
RSS_INSTANCES = [
    "https://nitter.perennialte.ch",
    "https://nitter.privacyredirect.com",
    "https://nitter.poast.org",
]

async def load_posted_urls(session: aiohttp.ClientSession) -> Tuple[Set[str], Optional[str]]:
    """Load cached tweet IDs from GitHub API if configured, with local JSON file fallback."""
    # Attempt 1: Fetch from GitHub repository API
    if GITHUB_REPO:
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{CACHE_FILE}?ref={GITHUB_BRANCH}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "TamilNewsBot",
        }
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

        try:
            async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content_b64 = data.get("content", "")
                    sha = data.get("sha")
                    decoded_bytes = base64.b64decode(content_b64)
                    loaded_list = json.loads(decoded_bytes.decode("utf-8"))
                    urls = set(loaded_list)
                    logging.info(f"Loaded {len(urls)} cached tweet IDs from GitHub repo ({GITHUB_REPO}) [sha: {sha[:7] if sha else 'none'}]")
                    # Sync to local cache file as backup
                    try:
                        with open(CACHE_FILE, "w", encoding="utf-8") as f:
                            json.dump(sorted(list(urls))[-MAX_CACHE_SIZE:], f, indent=2)
                    except Exception:
                        pass
                    return urls, sha
                elif resp.status == 404:
                    logging.info(f"Cache file {CACHE_FILE} not found on GitHub repo, will create upon first post.")
                    return set(), None
                else:
                    logging.warning(f"GitHub API cache fetch returned HTTP {resp.status}, falling back to local file.")
        except Exception as e:
            logging.warning(f"Error fetching cache from GitHub API ({e}), falling back to local file.")

    # Attempt 2: Local JSON file fallback
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                urls = set(json.load(f))
                logging.info(f"Loaded {len(urls)} cached tweet IDs from local file.")
                return urls, None
        except Exception as e:
            logging.error(f"Error reading local cache file: {e}")

    return set(), None

async def save_posted_urls(session: aiohttp.ClientSession, posted_urls: set, file_sha: Optional[str] = None):
    """Save seen tweet IDs to local JSON file and push back to GitHub repository if configured."""
    sorted_urls = sorted(list(posted_urls))
    payload_data = sorted_urls[-MAX_CACHE_SIZE:]

    # 1. Local file write
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload_data, f, indent=2)
    except Exception as e:
        logging.error(f"Error saving local cache file: {e}")

    # 2. GitHub repository API commit
    if GITHUB_TOKEN and GITHUB_REPO:
        content_str = json.dumps(payload_data, indent=2) + "\n"
        content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{CACHE_FILE}"
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "TamilNewsBot",
        }

        # Resolve latest SHA if missing
        current_sha = file_sha
        if not current_sha:
            try:
                async with session.get(f"{api_url}?ref={GITHUB_BRANCH}", headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        info = await resp.json()
                        current_sha = info.get("sha")
            except Exception:
                pass

        body = {
            "message": "auto: update posted_tweets.json cache [skip ci]",
            "content": content_b64,
            "branch": GITHUB_BRANCH,
        }
        if current_sha:
            body["sha"] = current_sha

        try:
            async with session.put(api_url, headers=headers, json=body, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status in (200, 201):
                    logging.info(f"Successfully committed updated cache to GitHub repo ({GITHUB_REPO})")
                    return
                elif resp.status == 409:
                    # Conflict: re-fetch SHA and retry once
                    logging.info("Conflict updating GitHub cache; retrying with latest SHA...")
                    async with session.get(f"{api_url}?ref={GITHUB_BRANCH}", headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as get_resp:
                        if get_resp.status == 200:
                            info = await get_resp.json()
                            body["sha"] = info.get("sha")
                            async with session.put(api_url, headers=headers, json=body, timeout=aiohttp.ClientTimeout(total=10)) as retry_resp:
                                if retry_resp.status in (200, 201):
                                    logging.info(f"Successfully committed updated cache to GitHub repo on retry ({GITHUB_REPO})")
                                    return
                resp_text = await resp.text()
                logging.warning(f"GitHub API update returned HTTP {resp.status}: {resp_text}")
        except Exception as e:
            logging.error(f"Failed to commit updated cache to GitHub: {e}")

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
                    else:
                        logging.info(f"Direct scrape from {domain} for @{account} returned HTTP 200 but found 0 status IDs")
                else:
                    logging.info(f"Direct scrape from {domain} for @{account} returned HTTP {response.status}")
        except Exception as e:
            logging.info(f"Direct scrape from {domain} for @{account} failed: {e}")

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
                    else:
                        logging.info(f"RSS mirror {instance} for @{account} returned 0 valid entries (title: '{title}')")
                else:
                    logging.info(f"RSS mirror {instance} for @{account} returned HTTP {response.status}")
        except Exception as e:
            logging.info(f"RSS mirror {instance} failed for @{account}: {e}")

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

async def run_feed_check() -> dict:
    """Core logic to check accounts, dispatch new tweets to Discord, and persist cache."""
    if not WEBHOOK_URL or WEBHOOK_URL == "YOUR_DISCORD_WEBHOOK_URL_HERE":
        logging.error("DISCORD_WEBHOOK_URL environment variable is missing or invalid.")
        return {"status": "error", "message": "DISCORD_WEBHOOK_URL missing or invalid"}

    start_time = time.time()
    now = time.time()
    all_unposted_tweets = []

    try:
        async with aiohttp.ClientSession() as session:
            posted_urls, file_sha = await load_posted_urls(session)
            is_first_run = len(posted_urls) == 0

            # Step 1: FETCH (In parallel using asyncio.gather)
            tasks = [fetch_tweets_for_account(session, account, posted_urls, is_first_run, now) for account in ACCOUNTS]
            results = await asyncio.gather(*tasks)

            for account_tweets in results:
                all_unposted_tweets.extend(account_tweets)

            if not all_unposted_tweets:
                logging.info("No new tweets to post.")
                return {
                    "status": "ok",
                    "new_tweets": 0,
                    "accounts_checked": len(ACCOUNTS),
                    "duration_seconds": round(time.time() - start_time, 2)
                }

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
                await save_posted_urls(session, posted_urls, file_sha)
                
        duration = round(time.time() - start_time, 2)
        logging.info(f"Feed Monitor execution finished successfully in {duration}s.")
        return {
            "status": "ok",
            "new_tweets": newly_posted,
            "total_candidates": len(all_unposted_tweets),
            "duration_seconds": duration
        }
    except Exception as e:
        logging.exception(f"Error executing feed monitor: {e}")
        return {"status": "error", "message": str(e)}

async def handle_root(request: web.Request) -> web.Response:
    """Health check / information page."""
    html_content = (
        "<html><head><title>Tamil News Bot</title></head>"
        "<body style='font-family: sans-serif; text-align: center; padding: 50px;'>"
        "<h1>📰 Tamil News Bot Webhook Service</h1>"
        "<p>Service is active and healthy.</p>"
        "<p>Send a GET or POST request to <code>/run</code> to trigger a feed check.</p>"
        "</body></html>"
    )
    return web.Response(text=html_content, content_type="text/html")

async def handle_healthz(request: web.Request) -> web.Response:
    """Standard health check endpoint for monitoring."""
    return web.Response(text="OK", status=200)

async def handle_run(request: web.Request) -> web.Response:
    """Webhook endpoint triggered by cron-job.org or manual ping."""
    # Optional authorization via secret token
    if CRON_SECRET:
        auth_header = request.headers.get("Authorization", "")
        token_param = request.query.get("token", "")
        expected_header = f"Bearer {CRON_SECRET}"
        if auth_header != expected_header and token_param != CRON_SECRET:
            return web.json_response(
                {"status": "unauthorized", "message": "Invalid or missing token."},
                status=401
            )

    # Concurrency control: prevent simultaneous overlapping executions
    if run_lock.locked():
        return web.json_response(
            {"status": "busy", "message": "A feed check is currently in progress."},
            status=429
        )

    async with run_lock:
        result = await run_feed_check()
        status_code = 200 if result.get("status") == "ok" else 500
        return web.json_response(result, status=status_code)

def create_app() -> web.Application:
    """Create and configure the aiohttp web application."""
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/healthz", handle_healthz)
    app.router.add_get("/run", handle_run)
    app.router.add_post("/run", handle_run)
    return app

if __name__ == "__main__":
    is_cli = "--cli" in sys.argv or (not PORT and "--server" not in sys.argv)
    if is_cli:
        logging.info("Running in CLI mode...")
        result = asyncio.run(run_feed_check())
        if result.get("status") == "error":
            sys.exit(1)
    else:
        server_port = int(PORT) if PORT else 8080
        logging.info(f"Starting Web Service on port {server_port} for cron-job.org triggers...")
        app = create_app()
        web.run_app(app, host="0.0.0.0", port=server_port)


