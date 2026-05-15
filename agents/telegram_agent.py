"""
Telegram Agent
==============
Sends notifications and handles human-in-the-loop approvals via Telegram.

Setup:
  1. Message @BotFather → /newbot → copy token
  2. Message your bot, then GET https://api.telegram.org/bot<TOKEN>/getUpdates
     to find your TELEGRAM_CHAT_ID
  3. Set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env

Features:
  - Book launch notifications (title, cover, platforms, price)
  - Revenue milestone alerts
  - Approve / reject pending book launches
  - Daily revenue digest
  - Heartbeat failure alerts
"""
import logging
import os
import time
from typing import Optional

import requests

log = logging.getLogger("telegram")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
BASE_URL  = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ""

# Pending approval queue: { message_id: {"action": callable, "data": dict} }
_pending: dict = {}


def _post(method: str, payload: dict) -> dict:
    if not BOT_TOKEN or not CHAT_ID:
        log.debug("Telegram not configured — skipping")
        return {}
    try:
        r = requests.post(f"{BASE_URL}/{method}", json=payload, timeout=10)
        return r.json()
    except Exception as e:
        log.error("Telegram %s failed: %s", method, e)
        return {}


def send_message(text: str, parse_mode: str = "HTML") -> dict:
    return _post("sendMessage", {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
    })


def send_book_launch_notification(brief: dict, platforms: list[str], price_usd: float = 4.99) -> dict:
    """Notify when a new book goes live on all platforms."""
    title = brief.get("title", "Untitled")
    niche = brief.get("niche", "")
    language = brief.get("language", "en").upper()
    platform_str = " | ".join(platforms) if platforms else "all platforms"

    text = (
        f"<b>NEW BOOK LIVE</b>\n\n"
        f"<b>{title}</b>\n"
        f"Niche: {niche}  |  Language: {language}\n"
        f"Price: ${price_usd:.2f} USD\n"
        f"Platforms: {platform_str}\n\n"
        f"Revenue tracking active."
    )
    return send_message(text)


def send_approval_request(
    brief: dict,
    approve_callback,
    reject_callback=None,
    timeout_seconds: int = 300,
) -> bool:
    """
    Send a book approval request and wait for user response.
    Returns True if approved (or timeout with auto-approve after timeout_seconds).
    """
    title = brief.get("title", "Untitled")
    niche = brief.get("niche", "")

    text = (
        f"<b>APPROVAL REQUIRED</b>\n\n"
        f"Book: <b>{title}</b>\n"
        f"Niche: {niche}\n\n"
        f"Reply <b>yes</b> to approve, <b>no</b> to reject.\n"
        f"(Auto-approves in {timeout_seconds // 60} minutes)"
    )

    resp = send_message(text)
    if not resp:
        log.info("Telegram not configured — auto-approving '%s'", title)
        if approve_callback:
            approve_callback()
        return True

    # Poll for reply
    last_update_id = 0
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        updates = _post("getUpdates", {
            "offset": last_update_id + 1,
            "timeout": 10,
            "allowed_updates": ["message"],
        })
        for update in (updates.get("result") or []):
            last_update_id = update.get("update_id", last_update_id)
            msg = update.get("message", {})
            if str(msg.get("chat", {}).get("id", "")) == str(CHAT_ID):
                reply = msg.get("text", "").strip().lower()
                if reply in ("yes", "y", "approve", "ok"):
                    send_message(f"Approved: <b>{title}</b>. Publishing now.")
                    if approve_callback:
                        approve_callback()
                    return True
                elif reply in ("no", "n", "reject", "cancel"):
                    send_message(f"Rejected: <b>{title}</b>. Skipping.")
                    if reject_callback:
                        reject_callback()
                    return False

    # Timeout — auto-approve
    send_message(f"Timeout reached — auto-approving: <b>{title}</b>")
    if approve_callback:
        approve_callback()
    return True


def send_revenue_milestone(milestone_label: str, total_aud: float):
    text = (
        f"<b>REVENUE MILESTONE</b>\n\n"
        f"Your empire has reached: <b>{milestone_label}</b>\n"
        f"Total AUD: <b>${total_aud:,.2f}</b>\n\n"
        f"Payout will be triggered automatically."
    )
    send_message(text)


def send_daily_digest(report: dict):
    total = report.get("total_revenue_usd", 0)
    products = report.get("total_published_products", 0)
    today = report.get("today_usd", 0)

    text = (
        f"<b>DAILY DIGEST</b>\n\n"
        f"Today: <b>${today:.2f}</b>\n"
        f"All-time: <b>${total:.2f}</b>\n"
        f"Products live: <b>{products}</b>\n"
    )
    send_message(text)


def send_alert(message: str):
    """Send a plain alert (heartbeat failures, payout issues, etc.)."""
    send_message(f"<b>ALERT</b>\n\n{message}")


def send_payout_notification(amount_aud: float, status: str):
    icon = "✅" if status == "paid" else "⚠️"
    text = (
        f"{icon} <b>PAYOUT {status.upper()}</b>\n\n"
        f"Amount: <b>AUD ${amount_aud:,.2f}</b>\n"
        f"Destination: CommBank Business Account\n"
        f"Status: {status}"
    )
    send_message(text)
