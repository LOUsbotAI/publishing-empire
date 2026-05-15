#!/usr/bin/env python3
"""
Go-Live Verification
====================
Run this before going public. Checks every service is correctly
configured for REAL money, REAL data, REAL transfers.

Usage: python3 go_live_check.py
"""
import sys
import os
import json
import requests
from pathlib import Path

# Load env
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "
INFO = "ℹ️ "

results = []
all_ok = True


def check(label: str, fn, required: bool = True):
    global all_ok
    try:
        detail = fn()
        results.append((PASS, label, detail or ""))
    except Exception as e:
        symbol = FAIL if required else WARN
        results.append((symbol, label, str(e)[:100]))
        if required:
            all_ok = False


# ── 1. ENVIRONMENT ─────────────────────────────────────────────────────────

check("ANTHROPIC_API_KEY set",
      lambda: "set" if os.getenv("ANTHROPIC_API_KEY", "").startswith("sk-ant-") else (_ for _ in ()).throw(ValueError("Not set or wrong format")))

check("STRIPE_SECRET_KEY is LIVE (not test)",
      lambda: "live key detected" if os.getenv("STRIPE_SECRET_KEY", "").startswith("sk_live_") else (_ for _ in ()).throw(ValueError("Key missing or is TEST key (sk_test_) — must use sk_live_ for real payments")))

check("STRIPE_WEBHOOK_SECRET set",
      lambda: "set" if os.getenv("STRIPE_WEBHOOK_SECRET", "") else (_ for _ in ()).throw(ValueError("Not set — add this from Stripe Dashboard → Webhooks")))

check("CF_TUNNEL_TOKEN set", required=False,
      fn=lambda: "set" if os.getenv("CF_TUNNEL_TOKEN") else (_ for _ in ()).throw(ValueError("Not set — store won't be publicly accessible")))

check("ELEVENLABS_API_KEY set", required=False,
      fn=lambda: "set" if os.getenv("ELEVENLABS_API_KEY") else (_ for _ in ()).throw(ValueError("Not set — audio production disabled")))

check("GUMROAD_ACCESS_TOKEN set", required=False,
      fn=lambda: "set" if os.getenv("GUMROAD_ACCESS_TOKEN") else (_ for _ in ()).throw(ValueError("Not set — direct sales disabled")))

check("ADMIN_KEY set (protects /admin endpoints)",
      lambda: "set" if os.getenv("ADMIN_KEY") else (_ for _ in ()).throw(ValueError("ADMIN_KEY not set — /admin endpoints are unprotected!")))

# ── 2. STRIPE LIVE CONNECTIVITY ─────────────────────────────────────────────

def check_stripe_live():
    key = os.getenv("STRIPE_SECRET_KEY", "")
    r = requests.get("https://api.stripe.com/v1/balance",
                     auth=(key, ""), timeout=10)
    r.raise_for_status()
    data = r.json()
    avail = sum(b["amount"] for b in data.get("available", [])) / 100
    pending = sum(b["amount"] for b in data.get("pending", [])) / 100
    return f"Available: ${avail:.2f} | Pending: ${pending:.2f}"

check("Stripe API responds (live mode)", check_stripe_live)

def check_stripe_bank():
    key = os.getenv("STRIPE_SECRET_KEY", "")
    r = requests.get("https://api.stripe.com/v1/account",
                     auth=(key, ""), timeout=10)
    r.raise_for_status()
    acct = r.json()
    payouts_enabled = acct.get("payouts_enabled", False)
    charges_enabled = acct.get("charges_enabled", False)
    if not charges_enabled:
        raise ValueError("charges_enabled=False — Stripe account not approved for live payments")
    if not payouts_enabled:
        raise ValueError("payouts_enabled=False — link a bank account in Stripe Dashboard")
    country = acct.get("country", "?")
    currency = acct.get("default_currency", "?").upper()
    return f"Charges: ✓ | Payouts: ✓ | Country: {country} | Currency: {currency}"

check("Stripe account can charge + payout", check_stripe_bank)

def check_stripe_webhook():
    key = os.getenv("STRIPE_SECRET_KEY", "")
    r = requests.get("https://api.stripe.com/v1/webhook_endpoints",
                     auth=(key, ""), timeout=10)
    r.raise_for_status()
    endpoints = r.json().get("data", [])
    if not endpoints:
        raise ValueError("No webhook endpoints registered — add your /webhook/stripe URL in Stripe Dashboard")
    active = [e for e in endpoints if e.get("status") == "enabled"]
    urls = [e["url"] for e in active]
    return f"{len(active)} active webhooks: {', '.join(urls[:2])}"

check("Stripe webhooks registered", check_stripe_webhook)

# ── 3. ANTHROPIC ────────────────────────────────────────────────────────────

def check_anthropic():
    key = os.getenv("ANTHROPIC_API_KEY", "")
    r = requests.get("https://api.anthropic.com/v1/models",
                     headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                     timeout=10)
    r.raise_for_status()
    models = [m["id"] for m in r.json().get("data", [])[:3]]
    return f"Models: {', '.join(models)}"

check("Anthropic API (content generation)", check_anthropic)

# ── 4. DATABASE ─────────────────────────────────────────────────────────────

def check_db():
    sys.path.insert(0, str(Path(__file__).parent))
    import database as db
    db.init_db()
    with db.conn() as c:
        tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return f"{len(tables)} tables: {', '.join(t['name'] for t in tables)}"

check("SQLite database initializes", check_db)

# ── 5. OPTIONAL SERVICES ────────────────────────────────────────────────────

def check_elevenlabs():
    key = os.getenv("ELEVENLABS_API_KEY", "")
    if not key:
        raise ValueError("Not configured")
    r = requests.get("https://api.elevenlabs.io/v1/user",
                     headers={"xi-api-key": key}, timeout=10)
    r.raise_for_status()
    u = r.json()
    chars_left = u.get("subscription", {}).get("character_limit", 0) - u.get("subscription", {}).get("character_count", 0)
    return f"Characters remaining: {chars_left:,}"

check("ElevenLabs TTS", check_elevenlabs, required=False)

def check_gumroad():
    token = os.getenv("GUMROAD_ACCESS_TOKEN", "")
    if not token:
        raise ValueError("Not configured")
    r = requests.get("https://api.gumroad.com/v2/user",
                     params={"access_token": token}, timeout=10)
    r.raise_for_status()
    return f"Seller: {r.json().get('user', {}).get('name', 'ok')}"

check("Gumroad (direct sales)", check_gumroad, required=False)

# ── REPORT ──────────────────────────────────────────────────────────────────

print()
print("━" * 60)
print("  PUBLISHING EMPIRE — GO-LIVE CHECK")
print("━" * 60)
print()
for symbol, label, detail in results:
    print(f"  {symbol}  {label}")
    if detail:
        print(f"       {detail}")
print()
print("━" * 60)
if all_ok:
    print("  ✅  ALL REQUIRED CHECKS PASSED — READY FOR LIVE TRAFFIC")
    print()
    print("  Next steps:")
    print("  1. Run: ./start.sh")
    print("  2. Point your domain DNS to your Cloudflare tunnel")
    print("  3. Set STRIPE_WEBHOOK_SECRET in .env (from Stripe Dashboard)")
    print("  4. Stripe will auto-payout to your bank on schedule")
else:
    print("  ❌  FIX THE FAILED CHECKS ABOVE BEFORE GOING LIVE")
print("━" * 60)
print()

sys.exit(0 if all_ok else 1)
