"""
DWC Havelock Stock Monitor
Multi-strategy checker with Telegram / email alerts.
"""

import os
import sys
import json
import smtplib
import requests
import warnings
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

warnings.filterwarnings("ignore")

PRODUCT_HANDLE  = "dwc-havelock"
SHOP_DOMAIN     = "delhiwatchcompany.com"
PRODUCT_URL     = f"https://{SHOP_DOMAIN}/products/{PRODUCT_HANDLE}"
CHECK_TIMEOUT   = 20

TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT   = os.environ.get("TELEGRAM_CHAT_ID", "")
EMAIL_FROM      = os.environ.get("EMAIL_FROM", "")
EMAIL_PASSWORD  = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_TO        = os.environ.get("EMAIL_TO", "")
SMTP_HOST       = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT       = int(os.environ.get("SMTP_PORT", "587"))

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

def _ua():
    import random
    return random.choice(USER_AGENTS)

def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": _ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Referer": f"https://{SHOP_DOMAIN}/",
    })
    return s

def check_via_products_js():
    url = f"https://{SHOP_DOMAIN}/products.json?limit=250"
    try:
        r = _session().get(url, timeout=CHECK_TIMEOUT)
        r.raise_for_status()
        products = r.json().get("products", [])
        for p in products:
            if p.get("handle") == PRODUCT_HANDLE:
                variants = p.get("variants", [])
                available = [v for v in variants if v.get("available")]
                return {"available": len(available) > 0, "variants": available, "all_variants": variants, "error": None, "method": "products.json"}
        return {"available": False, "variants": [], "all_variants": [], "error": None, "method": "products.json (not listed)"}
    except Exception as e:
        return {"available": False, "variants": [], "all_variants": [], "error": str(e), "method": "products.json"}

def check_via_product_json():
    url = f"https://{SHOP_DOMAIN}/products/{PRODUCT_HANDLE}.json"
    try:
        r = _session().get(url, timeout=CHECK_TIMEOUT)
        r.raise_for_status()
        variants = r.json().get("product", {}).get("variants", [])
        available = [v for v in variants if v.get("available")]
        return {"available": len(available) > 0, "variants": available, "all_variants": variants, "error": None, "method": "product.json"}
    except Exception as e:
        return {"available": False, "variants": [], "all_variants": [], "error": str(e), "method": "product.json"}

def check_via_html():
    try:
        s = _session()
        s.get(f"https://{SHOP_DOMAIN}/", timeout=CHECK_TIMEOUT)
        r = s.get(PRODUCT_URL, timeout=CHECK_TIMEOUT)
        r.raise_for_status()
        html = r.text.lower()
        sold_out = any(x in html for x in ["sold out", "sold-out", '"available":false', "out of stock"])
        in_stock  = any(x in html for x in ['"available":true', "add to cart", "add_to_cart"])
        return {"available": in_stock and not sold_out, "variants": [], "all_variants": [], "error": None, "method": "html-scrape"}
    except Exception as e:
        return {"available": False, "variants": [], "all_variants": [], "error": str(e), "method": "html-scrape"}

def check_via_proxy():
    try:
        proxy = f"https://api.allorigins.win/get?url={requests.utils.quote(PRODUCT_URL)}"
        r = requests.get(proxy, timeout=CHECK_TIMEOUT)
        r.raise_for_status()
        html = r.json().get("contents", "").lower()
        sold_out = "sold out" in html or '"available":false' in html
        in_stock  = '"available":true' in html or "add to cart" in html
        return {"available": in_stock and not sold_out, "variants": [], "all_variants": [], "error": None, "method": "allorigins-proxy"}
    except Exception as e:
        return {"available": False, "variants": [], "all_variants": [], "error": str(e), "method": "allorigins-proxy"}

def check_stock():
    strategies = [
        ("Shopify products.json listing", check_via_products_js),
        ("Shopify single product.json",   check_via_product_json),
        ("HTML scrape (session warm-up)", check_via_html),
        ("allorigins CORS proxy",         check_via_proxy),
    ]
    for name, fn in strategies:
        print(f"  Trying: {name}...", end=" ", flush=True)
        result = fn()
        if result["error"]:
            print(f"failed ({result['error'][:70]})")
        else:
            print(f"OK  ->  {'IN STOCK' if result['available'] else 'sold out'}")
            return result
    print("  All strategies failed.")
    return {"available": False, "variants": [], "all_variants": [], "error": "all_failed", "method": "none"}

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("  [Telegram] Skipped - credentials not configured.")
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": message, "parse_mode": "Markdown"}, timeout=10)
        r.raise_for_status()
        print("  [Telegram] Alert sent.")
        return True
    except Exception as e:
        print(f"  [Telegram] Failed: {e}")
        return False

def send_email(subject, body):
    if not all([EMAIL_FROM, EMAIL_PASSWORD, EMAIL_TO]):
        print("  [Email] Skipped - credentials not configured.")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        msg.attach(MIMEText(body, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as srv:
            srv.starttls()
            srv.login(EMAIL_FROM, EMAIL_PASSWORD)
            srv.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print("  [Email] Alert sent.")
        return True
    except Exception as e:
        print(f"  [Email] Failed: {e}")
        return False

def notify(result):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    variant_lines = ""
    if result.get("variants"):
        lines = [f"  - {v.get('title','?')} - Rs.{v.get('price','?')}" for v in result["variants"]]
        variant_lines = "\n" + "\n".join(lines)
    tg = f"🟢 *DWC Havelock is IN STOCK!*\n\n🔗 [Buy now]({PRODUCT_URL})\n🕐 {now}{variant_lines}"
    email_html = f"""<html><body style="font-family:sans-serif;max-width:500px;margin:40px auto;">
  <h2 style="color:#2e7d32;">DWC Havelock is back in stock!</h2>
  <p>The watch you've been waiting for is now available.</p>
  <a href="{PRODUCT_URL}" style="display:inline-block;padding:12px 28px;background:#1565c0;
     color:#fff;border-radius:6px;text-decoration:none;font-size:15px;">Buy now</a>
  <p style="color:#999;font-size:12px;margin-top:32px;">Detected at {now}</p>
</body></html>"""
    send_telegram(tg)
    send_email("DWC Havelock is IN STOCK - buy now!", email_html)

STATE_FILE = "state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"available": False}

def save_state(result):
    with open(STATE_FILE, "w") as f:
        json.dump({
            "available": result["available"],
            "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "method": result.get("method", "unknown"),
            "variants": [v.get("title") for v in result.get("variants", [])],
        }, f, indent=2)

def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"\n{'='*55}")
    print(f"  DWC Havelock Stock Monitor  |  {now}")
    print(f"{'='*55}\n")

    prev = load_state()
    result = check_stock()

    print(f"\n  Final status : {'IN STOCK' if result['available'] else 'SOLD OUT'}")
    print(f"  Method used  : {result.get('method','?')}")

    if result["error"] == "all_failed":
        print("\n  All check strategies failed. Exiting without updating state.")
        sys.exit(1)

    save_state(result)

    if result["available"] and not prev.get("available", False):
        print("\n  TRANSITION: sold-out -> in stock! Sending alerts...")
        notify(result)
    elif result["available"]:
        print("\n  Already in stock - no new alert sent.")
    else:
        print("\n  Still sold out. No alert.")

    print(f"\n{'='*55}\n")

if __name__ == "__main__":
    main()
