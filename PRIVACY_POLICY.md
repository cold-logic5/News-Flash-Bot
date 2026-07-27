# Privacy Policy

**Last Updated:** July 27, 2026

## 1. Overview
This Privacy Policy describes how **News Flash** ("the Bot") handles data when running in your Discord server. We prioritize user privacy and practice strict data minimization.

## 2. Information We Collect
The Bot collects and stores only the minimal data necessary to function:
- **Discord Channel ID**: Configured to determine where news updates are dispatched.
- **Tweet Status IDs**: Temporarily stored in a local cache (`posted_tweets.json`, capped at 50 items) to prevent sending duplicate notifications.

## 3. Information We DO NOT Collect
- **User Messages & Chat History**: We do not read, log, store, or process user chat messages or personal conversations.
- **Personal Identifiable Information (PII)**: We do not collect names, email addresses, IP addresses, or personal identity profiles.
- **Payment Information**: The Bot does not request or process financial details.

## 4. How We Use Data
The minimal data stored is used exclusively to:
- Deliver news RSS updates to your designated Discord channel.
- Filter out already-posted updates to prevent channel spam.

## 5. Third-Party Services
News feed links are retrieved from public RSS mirrors and converted to `fxtwitter.com` URLs so Discord can automatically render video and image embeds. No user data is transmitted to third-party services.

## 6. Data Retention & Removal
- The local tweet cache automatically deletes old entries beyond the 50 most recent items.
- Removing the Bot from your Discord server immediately stops all data processing for your server.

## 7. Contact
If you have questions about this Privacy Policy, please reach out to the Bot administrator via your Discord server.
