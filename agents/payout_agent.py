"""
Payout Agent
============
Monitors Stripe balance, triggers payouts to bank account,
tracks payout history, and alerts on failed payouts.
Runs autonomously — no human needed.
"""
import logging
from datetime import datetime, timedelta

import requests
import config
import database as db

log = logging.getLogger("payout_agent")

STRIPE_BASE = "https://api.stripe.com/v1"


def _stripe(method: str, endpoint: str, data: dict = None, params: dict = None):
    auth = (config.STRIPE_SECRET_KEY, "")
    url = f"{STRIPE_BASE}/{endpoint}"
    if method == "GET":
        r = requests.get(url, auth=auth, params=params or {}, timeout=30)
    else:
        r = requests.post(url, auth=auth, data=data or {}, timeout=30)
    r.raise_for_status()
    return r.json()


def get_balance() -> dict:
    """Current Stripe balance — available vs pending."""
    b = _stripe("GET", "balance")
    available = {c["currency"]: c["amount"] / 100 for c in b.get("available", [])}
    pending   = {c["currency"]: c["amount"] / 100 for c in b.get("pending", [])}
    return {"available": available, "pending": pending}


def trigger_payout(amount_cents: int = None, currency: str = "usd") -> dict:
    """
    Send money from Stripe balance to the linked bank account.
    If amount_cents is None, pays out the full available balance.
    """
    balance = get_balance()
    available_cents = int(balance["available"].get(currency, 0) * 100)

    if available_cents <= 0:
        log.info("Payout skipped — no available balance")
        return {"status": "skipped", "reason": "zero_balance"}

    payout_amount = amount_cents if amount_cents else available_cents

    # Stripe minimum payout is $1
    if payout_amount < 100:
        log.info("Payout skipped — amount below minimum ($1): $%.2f", payout_amount / 100)
        return {"status": "skipped", "reason": "below_minimum"}

    payout = _stripe("POST", "payouts", {
        "amount": payout_amount,
        "currency": currency,
        "statement_descriptor": "Publishing Empire",
    })

    log.info("Payout initiated: $%.2f %s → bank (ETA: %s)",
             payout_amount / 100, currency.upper(),
             payout.get("arrival_date", "2-5 business days"))

    # Record in DB
    with db.conn() as c:
        c.execute(
            """INSERT INTO payout_log
               (stripe_payout_id, amount_usd, currency, status, initiated_at, eta)
               VALUES (?,?,?,?,?,?)""",
            (payout["id"], payout_amount / 100, currency,
             payout["status"], datetime.utcnow().isoformat(),
             str(payout.get("arrival_date", "")))
        )

    return {
        "status": "initiated",
        "payout_id": payout["id"],
        "amount_usd": payout_amount / 100,
        "eta": payout.get("arrival_date"),
    }


def get_payout_history(limit: int = 10) -> list[dict]:
    payouts = _stripe("GET", "payouts", params={"limit": limit})
    return [
        {
            "id": p["id"],
            "amount_usd": p["amount"] / 100,
            "status": p["status"],
            "arrival_date": datetime.fromtimestamp(p["arrival_date"]).strftime("%Y-%m-%d"),
            "initiated": datetime.fromtimestamp(p["created"]).strftime("%Y-%m-%d %H:%M"),
        }
        for p in payouts.get("data", [])
    ]


def set_automatic_payout_schedule(interval: str = "daily") -> dict:
    """
    Configure Stripe's automatic payout schedule.
    interval: 'daily' | 'weekly' | 'monthly'
    Stripe handles this — money moves to bank on schedule automatically.
    """
    if interval == "daily":
        schedule = {"interval": "daily"}
    elif interval == "weekly":
        schedule = {"interval": "weekly", "weekly_anchor": "monday"}
    else:
        schedule = {"interval": "monthly", "monthly_anchor": 1}

    result = _stripe("POST", "account", {
        "settings[payouts][schedule][interval]": schedule["interval"],
        **{f"settings[payouts][schedule][{k}]": str(v)
           for k, v in schedule.items() if k != "interval"},
        "settings[payouts][debit_negative_balances]": "true",
    })
    log.info("Payout schedule set to: %s", interval)
    return result


def check_and_payout_threshold(threshold_usd: float = 50.0) -> dict:
    """
    Auto-payout whenever balance exceeds the threshold.
    Called by orchestrator on a schedule.
    """
    balance = get_balance()
    available = balance["available"].get("usd", 0)
    log.info("Balance check — Available: $%.2f | Pending: $%.2f",
             available, balance["pending"].get("usd", 0))

    if available >= threshold_usd:
        log.info("Balance $%.2f exceeds threshold $%.2f — triggering payout",
                 available, threshold_usd)
        return trigger_payout()
    return {"status": "holding", "available_usd": available, "threshold_usd": threshold_usd}


def check_for_failed_payouts() -> list[dict]:
    """
    Alert on any failed payouts — runs daily so failures never go unnoticed.
    Returns list of failed payouts that need attention.
    """
    payouts = _stripe("GET", "payouts", params={"status": "failed", "limit": 100})
    failed = payouts.get("data", [])
    if failed:
        total = sum(p["amount"] for p in failed) / 100
        log.warning(
            "ALERT: %d FAILED PAYOUT(S) totalling $%.2f — bank account may need updating!",
            len(failed), total
        )
        for p in failed:
            log.warning("  Failed payout %s: $%.2f on %s — %s",
                        p["id"], p["amount"] / 100,
                        datetime.fromtimestamp(p["created"]).strftime("%Y-%m-%d"),
                        p.get("failure_message", "unknown reason"))
    else:
        log.info("Payout health: no failed payouts")
    return [{"id": p["id"], "amount_usd": p["amount"] / 100,
             "failure_message": p.get("failure_message"),
             "failure_code": p.get("failure_code"),
             "created": datetime.fromtimestamp(p["created"]).isoformat()}
            for p in failed]


def full_financial_status() -> dict:
    """Complete financial snapshot for the empire."""
    balance = get_balance()
    payouts = get_payout_history(5)
    revenue = db.revenue_summary()

    in_transit = sum(p["amount_usd"] for p in payouts if p["status"] == "in_transit")
    paid_out   = sum(p["amount_usd"] for p in payouts if p["status"] == "paid")

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "stripe_available_usd": balance["available"].get("usd", 0),
        "stripe_pending_usd": balance["pending"].get("usd", 0),
        "in_transit_usd": in_transit,
        "paid_to_bank_recent": paid_out,
        "all_time_revenue_usd": revenue["total_usd"],
        "revenue_by_platform": revenue["by_source"],
        "recent_payouts": payouts,
    }
