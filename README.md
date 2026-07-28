# X (Twitter) RSS Feed Discord Monitor (Webhook Edition)

This lightweight bot monitors X (Twitter) accounts via public RSS mirrors and dispatches updates directly to a **Discord Webhook** using `fxtwitter.com` links for rich media embeds (videos, images, text).

---

## ⚡ Why Webhooks?

- **No Bot Tokens or Gateway required**: Uses native HTTP POST requests.
- **Never goes offline / sleep**: Runs statelessly on a schedule (GitHub Actions or Render Cron).
- **100% Free**: Uses 0 paid resources or sleeping web servers.

---

## 🚀 Setup Instructions

### Step 1: Create a Discord Webhook
1. Open your Discord server.
2. Go to **Channel Settings** ➔ **Integrations** ➔ **Webhooks** ➔ **Create Webhook**.
3. Copy the **Webhook URL**.

---

### Step 2: Option A — GitHub Actions (Recommended & 100% Free)

1. Push this repository to your **GitHub account**.
2. Go to your Repository on GitHub ➔ **Settings** ➔ **Secrets and variables** ➔ **Actions**.
3. Click **New repository secret**:
   - **Name**: `DISCORD_WEBHOOK_URL`
   - **Value**: Your copied Discord Webhook URL
4. Go to the **Actions** tab in GitHub and ensure workflows are enabled.
5. The bot will automatically check feeds **every 10 minutes**!

---

### Step 3: Option B — Render Cron Job

If hosting on Render:
1. Create a **Cron Job** on Render.
2. **Build Command**: `pip install -r requirements.txt`
3. **Command**: `python main.py`
4. **Schedule**: `*/10 * * * *` (every 10 minutes)
5. Add `DISCORD_WEBHOOK_URL` in **Environment Variables**.

---

## 🛠 Local Testing

Create a `.env` file based on `.env.example`:
```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
ACCOUNTS=sunnewstamil,News18TamilNadu,polimernews,NewsTamilTV24x7
```

Run locally:
```bash
python main.py
```
