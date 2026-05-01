# DWC Havelock Stock Monitor

Automatically checks [delhiwatchcompany.com/products/dwc-havelock](https://delhiwatchcompany.com/products/dwc-havelock) every 15 minutes using GitHub Actions (100% free) and sends you a **Telegram** or **email** alert the moment it goes from sold-out → in stock.

Built for the Indian watch community. Fork it, set it up in 5 minutes, never miss a DWC drop again.

---

## How it works

- GitHub Actions runs `src/checker.py` on a cron schedule (every 15 min)
- Tries 4 strategies in order: Shopify products.json → product.json → HTML scrape → CORS proxy
- Caches sold-out/in-stock state between runs
- Alerts only on **transition** — no spam

---

## Setup

### 1. Fork this repo

Click **Fork** at the top right of this page.

### 2. Add your secrets

Go to your forked repo → **Settings → Secrets and variables → Actions → New repository secret**

#### Telegram (recommended)

| Secret | Value |
|---|---|
| `TELEGRAM_TOKEN` | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your numeric ID from @userinfobot |

> Send any message to your bot first so it can reply to you.

#### Email (Gmail)

| Secret | Value |
|---|---|
| `EMAIL_FROM` | your-gmail@gmail.com |
| `EMAIL_PASSWORD` | Gmail App Password (not your real password) |
| `EMAIL_TO` | Where to send the alert |

> You only need one of the two (Telegram or email).

### 3. Enable and test

Go to **Actions tab → DWC Havelock Stock Monitor → Run workflow** to trigger a manual test run.

---

## Customise the check interval

Edit `.github/workflows/stock-monitor.yml`:

```yaml
- cron: "*/15 * * * *"   # every 15 min (default)
- cron: "*/5 * * * *"    # every 5 min (fastest GitHub allows)
- cron: "0 * * * *"      # every hour
```

---

## Run locally

```bash
pip install requests
python src/checker.py
```

---

*Made with love for the Indian watch community. MIT Licensed.*
