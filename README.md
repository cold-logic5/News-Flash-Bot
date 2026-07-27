# X (Twitter) RSS Feed Discord Monitor

This bot monitors X (Twitter) accounts via `xcancel.com` RSS feeds and posts updates to Discord using `fxtwitter.com` links for rich media embeds (videos, images, text).

## 🚀 Setup Instructions

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment Variables**
   Create a `.env` file based on `.env.example`:
   ```env
   DISCORD_TOKEN=your_discord_bot_token_here
   CHANNEL_ID=1234567890123456789
   CHECK_INTERVAL_MINUTES=10
   ACCOUNTS=discord,twitter,github
   ```

3. **Run the Bot**
   ```bash
   python bot.py
   ```

## 🛠 Features & Improvements

- **Non-blocking Async I/O**: Uses `aiohttp` and `asyncio.to_thread` so feed parsing won't freeze the Discord bot loop.
- **Persistent Cache**: Saves seen tweet URLs to `posted_tweets.json` so bot restarts won't re-trigger past tweets.
- **Embed Optimization**: Automatically translates `xcancel.com` / `twitter.com` links into `fxtwitter.com` for full video/image rich previews in Discord channels.
- **Rate-limit Protection**: Includes built-in delays between feed calls and Discord message dispatches.
