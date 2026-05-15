"""
Heartbeat Agent
===============
Runs every 5 minutes. Checks every service connection is alive.
If anything is down, logs it and retries. Acts as the nervous system
of the empire — if a service dies, the orchestrator knows immediately.
"""
import logging
import time
from datetime import datetime

import requests
import config

log = logging.getLogger("heartbeat")

TIMEOUT = 10


def _ok(name: str, fn) -> dict:
    start = time.time()
    try:
        result = fn()
        latency = round((time.time() - start) * 1000)
        log.info("  ✅ %-25s %dms", name, latency)
        return {"service": name, "status": "ok", "latency_ms": latency, "detail": result}
    except Exception as e:
        log.warning("  ❌ %-25s %s", name, str(e)[:80])
        return {"service": name, "status": "down", "error": str(e)[:120]}


def check_anthropic() -> dict:
    return _ok("Anthropic API", lambda: (
        requests.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": config.ANTHROPIC_API_KEY,
                     "anthropic-version": "2023-06-01"},
            timeout=TIMEOUT
        ).raise_for_status() or "models endpoint reachable"
    ))


def check_stripe() -> dict:
    def _check():
        r = requests.get(
            "https://api.stripe.com/v1/balance",
            auth=(config.STRIPE_SECRET_KEY, ""),
            timeout=TIMEOUT
        )
        r.raise_for_status()
        data = r.json()
        avail = sum(b["amount"] for b in data.get("available", [])) / 100
        return f"balance available: ${avail:.2f}"
    return _ok("Stripe", _check)


def check_elevenlabs() -> dict:
    if not config.ELEVENLABS_API_KEY:
        return {"service": "ElevenLabs", "status": "not_configured"}
    return _ok("ElevenLabs TTS", lambda: (
        requests.get(
            "https://api.elevenlabs.io/v1/user",
            headers={"xi-api-key": config.ELEVENLABS_API_KEY},
            timeout=TIMEOUT
        ).raise_for_status() or "user endpoint reachable"
    ))


def check_gumroad() -> dict:
    if not config.GUMROAD_ACCESS_TOKEN:
        return {"service": "Gumroad", "status": "not_configured"}
    return _ok("Gumroad", lambda: (
        requests.get(
            "https://api.gumroad.com/v2/user",
            params={"access_token": config.GUMROAD_ACCESS_TOKEN},
            timeout=TIMEOUT
        ).raise_for_status() or "user reachable"
    ))


def check_mailchimp() -> dict:
    if not config.MAILCHIMP_API_KEY:
        return {"service": "Mailchimp", "status": "not_configured"}
    server = config.MAILCHIMP_SERVER_PREFIX
    return _ok("Mailchimp", lambda: (
        requests.get(
            f"https://{server}.api.mailchimp.com/3.0/ping",
            auth=("any", config.MAILCHIMP_API_KEY),
            timeout=TIMEOUT
        ).raise_for_status() or "ping ok"
    ))


def check_twitter() -> dict:
    if not config.TWITTER_API_KEY:
        return {"service": "Twitter/X", "status": "not_configured"}
    return _ok("Twitter/X", lambda: (
        requests.get(
            "https://api.twitter.com/2/users/me",
            headers={"Authorization": f"Bearer {config.TWITTER_ACCESS_TOKEN}"},
            timeout=TIMEOUT
        ).raise_for_status() or "user reachable"
    ))


def check_youtube() -> dict:
    if not config.YOUTUBE_REFRESH_TOKEN:
        return {"service": "YouTube", "status": "not_configured"}
    def _check():
        r = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": config.YOUTUBE_CLIENT_ID,
                "client_secret": config.YOUTUBE_CLIENT_SECRET,
                "refresh_token": config.YOUTUBE_REFRESH_TOKEN,
                "grant_type": "refresh_token",
            },
            timeout=TIMEOUT
        )
        r.raise_for_status()
        return "token refresh ok"
    return _ok("YouTube OAuth", _check)


def check_storefront(port: int = 8000) -> dict:
    return _ok("Storefront (local)", lambda: (
        requests.get(f"http://localhost:{port}/", timeout=TIMEOUT).raise_for_status()
        or "homepage reachable"
    ))


def check_database() -> dict:
    def _check():
        import database as db
        summary = db.revenue_summary()
        return f"revenue: ${summary['total_usd']:.2f}, events: {summary['events']}"
    return _ok("SQLite Database", _check)


def check_internet() -> dict:
    return _ok("Internet connectivity", lambda: (
        requests.get("https://1.1.1.1", timeout=5).ok or "reachable"
    ))


# ─── FULL HEARTBEAT ──────────────────────────────────────────────────────────

ALL_CHECKS = [
    check_internet,
    check_database,
    check_anthropic,
    check_stripe,
    check_elevenlabs,
    check_gumroad,
    check_mailchimp,
    check_twitter,
    check_youtube,
    check_storefront,
]


def run_heartbeat() -> dict:
    now = datetime.utcnow().isoformat()
    log.info("━━━ Heartbeat Check %s ━━━", now)

    results = [fn() for fn in ALL_CHECKS]

    ok = [r for r in results if r["status"] == "ok"]
    down = [r for r in results if r["status"] == "down"]
    unconf = [r for r in results if r["status"] == "not_configured"]

    status = "healthy" if not down else "degraded"
    log.info("━━━ %s — %d ok, %d down, %d unconfigured",
             status.upper(), len(ok), len(down), len(unconf))

    if down:
        log.warning("DOWN SERVICES: %s", ", ".join(r["service"] for r in down))

    return {
        "timestamp": now,
        "status": status,
        "ok": len(ok),
        "down": len(down),
        "not_configured": len(unconf),
        "services": results,
    }


def run_forever(interval_seconds: int = 300):
    """Run heartbeat checks on a loop — call from orchestrator or standalone."""
    log.info("Heartbeat agent started — checking every %ds", interval_seconds)
    while True:
        try:
            run_heartbeat()
        except Exception as e:
            log.error("Heartbeat run failed: %s", e)
        time.sleep(interval_seconds)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(message)s",
                        datefmt="%H:%M:%S")
    if "--once" in sys.argv:
        import json
        print(json.dumps(run_heartbeat(), indent=2))
    else:
        run_forever()
