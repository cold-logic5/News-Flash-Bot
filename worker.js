export default {
  // Triggered automatically by Cloudflare Scheduled Cron (every 5 or 10 minutes)
  async scheduled(event, env, ctx) {
    ctx.waitUntil(checkFeeds(env));
  },

  // HTTP endpoint for manual testing in browser (https://your-worker.subdomain.workers.dev)
  async fetch(request, env, ctx) {
    await checkFeeds(env);
    return new Response("RSS Feed Monitor executed successfully!", { status: 200 });
  }
};

const DEFAULT_ACCOUNTS = ["sunnewstamil", "News18TamilNadu", "polimernews", "NewsTamilTV24x7"];
const RSS_INSTANCES = [
  "https://nitter.net",
  "https://xcancel.com",
  "https://nitter.poast.org"
];

async function checkFeeds(env) {
  const webhookUrl = env.DISCORD_WEBHOOK_URL;
  if (!webhookUrl) {
    console.error("DISCORD_WEBHOOK_URL environment variable is missing.");
    return;
  }

  const accountsStr = env.ACCOUNTS || DEFAULT_ACCOUNTS.join(",");
  const accounts = accountsStr.split(",").map(a => a.trim()).filter(Boolean);

  // Load seen tweet IDs from Cloudflare KV storage (or memory)
  let seenTweets = [];
  try {
    if (env.TWEETS_KV) {
      const kvData = await env.TWEETS_KV.get("posted_tweets");
      if (kvData) {
        seenTweets = JSON.parse(kvData);
      }
    }
  } catch (e) {
    console.error("Error reading KV cache:", e);
  }

  const isFirstRun = seenTweets.length === 0;

  for (const account of accounts) {
    let feedXml = null;

    // Fetch RSS feed from working mirrors
    for (const instance of RSS_INSTANCES) {
      try {
        const res = await fetch(`${instance}/${account}/rss`, {
          headers: {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, */*"
          }
        });
        if (res.ok) {
          const text = await res.text();
          if (text.includes("<item>") && !text.toLowerCase().includes("whitelisted")) {
            feedXml = text;
            break;
          }
        }
      } catch (err) {
        console.log(`Error fetching ${instance}/${account}/rss:`, err);
      }
    }

    if (!feedXml) continue;

    // Extract item blocks from RSS XML
    const itemMatches = [...feedXml.matchAll(/<item>[\s\S]*?<\/item>/gi)];
    if (itemMatches.length === 0) continue;

    // On first run, check only the newest tweet; otherwise process from oldest to newest
    let itemsToProcess = isFirstRun ? [itemMatches[0]] : itemMatches.map(m => m[0]).reverse();

    for (const itemXml of itemsToProcess) {
      const statusMatch = itemXml.match(/\/status\/(\d+)/);
      if (!statusMatch) continue;

      const tweetId = statusMatch[1];
      const uniqueKey = `${account}_${tweetId}`;

      if (seenTweets.includes(uniqueKey)) continue;

      seenTweets.push(uniqueKey);

      // Format URL for rich Discord embeds
      const fxtwitterUrl = `https://fxtwitter.com/${account}/status/${tweetId}`;
      const message = `📰 **New update from @${account}**\n${fxtwitterUrl}`;

      // Dispatch Webhook to Discord
      try {
        await fetch(webhookUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: message })
        });
        console.log(`Posted update for @${account}: ${fxtwitterUrl}`);
      } catch (err) {
        console.error("Error posting to Discord Webhook:", err);
      }

      await new Promise(r => setTimeout(r, 1200));
    }
  }

  // Keep max 50 items in KV cache
  const trimmedCache = seenTweets.slice(-50);
  if (env.TWEETS_KV) {
    try {
      await env.TWEETS_KV.put("posted_tweets", JSON.stringify(trimmedCache));
    } catch (e) {
      console.error("Error saving to KV:", e);
    }
  }
}
