# X (Twitter) RSS Feed Discord Monitor (Webhook + cron-job.org Edition)

This lightweight bot monitors Tamil news accounts on X (Twitter) and dispatches updates directly to a **Discord Webhook** using `fxtwitter.com` links for rich media embeds (videos, images, text).

---

## ⚡ Why Render Web Service + cron-job.org?

- **100% Free**: Operates entirely within Render's Free Web Service tier (750 free hours/month) and cron-job.org's free plan.
- **Never Goes to Sleep**: Free Render web services normally spin down after 15 minutes of inactivity. Since **cron-job.org pings it every 5 minutes**, the service **stays warm 24/7**!
- **Reliable Datacenter IPs**: Unlike GitHub Actions datacenter IP pools (which X/Twitter aggressively blocks), Render's IPs reliably fetch updates.
- **Cache Persistence**: Automatically syncs `posted_tweets.json` with your GitHub repository via the GitHub Contents API so deduplication survives container restarts.

---

## 🚀 Setup Guide

### Step 1: Create a Discord Webhook
1. Open your Discord server.
2. Go to **Channel Settings** ➔ **Integrations** ➔ **Webhooks** ➔ **New Webhook**.
3. Copy the **Webhook URL**.

---

### Step 2: Create a GitHub Personal Access Token (PAT)
To allow the service to save seen tweet IDs back to this repository:
1. On GitHub, go to: **Settings** ➔ **Developer settings** ➔ **Personal access tokens** ➔ **Fine-grained tokens** (or [click here](https://github.com/settings/tokens?type=beta)).
2. Click **Generate new token**:
   - **Token name**: `Render News Bot Cache`
   - **Repository access**: Select `Only select repositories` ➔ choose `News-Flash-Bot`.
   - **Repository permissions**: Under **Contents**, set to `Read and write`.
3. Click **Generate token** and copy the value (`github_pat_...`).

---

### Step 3: Deploy to Render (Free Web Service)

#### Option A: Using Render Blueprints (Automatic)
1. Go to your [Render Dashboard](https://dashboard.render.com).
2. Click **Blueprints** ➔ **New Blueprint Instance**.
3. Connect your repository `cold-logic5/News-Flash-Bot` (`master` branch).
4. Render will read `render.yaml` and configure the web service.
5. Provide the environment variables when prompted:
   - `DISCORD_WEBHOOK_URL`: Your Discord Webhook URL
   - `GITHUB_TOKEN`: The GitHub PAT created in Step 2
   - `CRON_SECRET`: *(Optional)* A secret password to protect your `/run` endpoint
6. Click **Apply**. Once deployed, copy your service URL (e.g., `https://tamil-news-bot-xxxx.onrender.com`).

#### Option B: Manual Web Service Setup
1. In Render Dashboard, click **New +** ➔ **Web Service**.
2. Connect your repository `cold-logic5/News-Flash-Bot`.
3. Fill in:
   - **Name**: `tamil-news-bot`
   - **Language / Runtime**: `Python`
   - **Branch**: `master`
   - **Plan**: `Free`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
4. In **Environment Variables**, add:
   - `DISCORD_WEBHOOK_URL`: `<your-discord-webhook-url>`
   - `ACCOUNTS`: `sunnewstamil,News18TamilNadu,polimernews`
   - `GITHUB_REPO`: `cold-logic5/News-Flash-Bot`
   - `GITHUB_BRANCH`: `master`
   - `GITHUB_TOKEN`: `<your-github-pat>`
   - `CRON_SECRET`: *(Optional)* `<a-secret-passphrase>`
5. Click **Create Web Service**. Copy your live URL when ready.

---

### Step 4: Configure cron-job.org

1. Register or log in to [cron-job.org](https://cron-job.org).
2. Go to **Cronjobs** ➔ click **Create cronjob**.
3. Configure the settings:
   - **Title**: `Tamil News Bot Trigger`
   - **URL**: `https://<your-service-name>.onrender.com/run`
     *(If you set a `CRON_SECRET`, use: `https://<your-service-name>.onrender.com/run?token=YOUR_CRON_SECRET`)*
   - **Execution schedule**: Choose `Every 5 minutes` (or `User-defined: */5 * * * *`).
   - **Request method**: `GET`
4. Under **Advanced settings**:
   - **Request timeout**: `30 seconds`
5. Click **Create**.

Your bot is now live! Every 5 minutes, cron-job.org pings `/run`, checking all tracked accounts, posting new tweets to Discord, updating the cache on GitHub, and keeping Render awake!

---

## 🛠 Local Testing

### Standalone CLI Mode
Run once directly without starting a server:
```bash
python main.py --cli
```

### Local Web Server Mode
Test the web server on port 8080:
```bash
python main.py --server
```
Then in your browser or terminal:
- Health check: `http://localhost:8080/`
- Trigger feed check: `http://localhost:8080/run`
