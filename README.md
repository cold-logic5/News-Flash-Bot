# X (Twitter) RSS Feed Discord Monitor (Webhook Edition)

This lightweight bot monitors Tamil news X (Twitter) accounts and dispatches updates directly to a **Discord Webhook** using `fxtwitter.com` links for rich media embeds (videos, images, text).

---

## ⚡ Why Webhooks & Render?

- **No Bot Tokens or Gateway required**: Uses native HTTP POST requests.
- **Reliable Datacenter IPs**: Render Cron Job instances are far less likely to be blocked by X/Twitter compared to GitHub Actions runner IP pools.
- **Cache Persistence**: Automatically reads and commits `posted_tweets.json` back to your GitHub repository using the GitHub API so deduplication persists across ephemeral Render containers.
- **100% Free**: Operates comfortably within the free tier.

---

## 🚀 Setup Instructions

### Step 1: Create a Discord Webhook
1. Open your Discord server.
2. Go to **Channel Settings** ➔ **Integrations** ➔ **Webhooks** ➔ **New Webhook**.
3. Copy the **Webhook URL**.

---

### Step 2: Create a GitHub Personal Access Token (PAT)
To allow Render to save posted tweet history back to this repository:
1. On GitHub, go to **Settings** ➔ **Developer settings** ➔ **Personal access tokens** ➔ **Fine-grained tokens** (or Tokens classic).
2. Click **Generate new token**:
   - **Token name**: `Render News Bot Cache`
   - **Repository access**: Only select `cold-logic5/News-Flash-Bot`
   - **Permissions**:
     - **Contents**: `Read and write`
3. Generate the token and copy the value (`github_pat_...` or `ghp_...`).

---

### Step 3: Deploy to Render (Primary - Recommended)

#### Option A: Using Render Blueprints (Automatic Setup)
1. Log in to [Render Dashboard](https://dashboard.render.com).
2. Click **Blueprints** ➔ **New Blueprint Instance**.
3. Connect your repository (`News-Flash-Bot`).
4. Render will read `render.yaml` and configure the Cron Job (`tamil-news-bot`).
5. Provide the two required environment variables when prompted:
   - `DISCORD_WEBHOOK_URL`: Your Discord webhook URL
   - `GITHUB_TOKEN`: Your GitHub Personal Access Token generated in Step 2
6. Click **Apply**. Render will run the bot every 5 minutes (`*/5 * * * *`).

#### Option B: Manual Setup on Render
1. In Render Dashboard, click **New +** ➔ **Cron Job**.
2. Connect your `News-Flash-Bot` repository.
3. Configure the job:
   - **Name**: `tamil-news-bot`
   - **Schedule**: `*/5 * * * *`
   - **Runtime**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
4. In the **Environment Variables** section, add:
   - `DISCORD_WEBHOOK_URL`: `<your-discord-webhook-url>`
   - `ACCOUNTS`: `sunnewstamil,News18TamilNadu,polimernews`
   - `GITHUB_REPO`: `cold-logic5/News-Flash-Bot`
   - `GITHUB_BRANCH`: `master`
   - `GITHUB_TOKEN`: `<your-github-pat>`
5. Click **Create Cron Job**.

---

### Step 4: GitHub Actions (Backup Runner)

The repository retains `.github/workflows/rss_monitor.yml` as an automated backup.
If Render is active, you can keep GitHub Actions running as a fallback or disable it in GitHub ➔ **Actions** tab if you only want Render to execute.

---

## 🛠 Local Testing

Create a `.env` file based on `.env.example`:
```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
ACCOUNTS=sunnewstamil,News18TamilNadu,polimernews
GITHUB_REPO=cold-logic5/News-Flash-Bot
GITHUB_BRANCH=master
GITHUB_TOKEN=ghp_... # optional for local testing
```

Run locally:
```bash
python main.py
```
