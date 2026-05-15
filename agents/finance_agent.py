"""
Tracks revenue across all platforms, reconciles with Stripe,
and generates financial reports.
"""
import logging
from datetime import datetime, timedelta

import requests
import config
import database as db

log = logging.getLogger(__name__)


# ─── STRIPE ──────────────────────────────────────────────────────────────────

def sync_stripe_revenue(days_back: int = 7):
    """Pull recent Stripe charges and record them in the database."""
    if not config.STRIPE_SECRET_KEY:
        log.warning("Stripe not configured — skipping revenue sync")
        return

    since = int((datetime.utcnow() - timedelta(days=days_back)).timestamp())
    resp = requests.get(
        "https://api.stripe.com/v1/charges",
        auth=(config.STRIPE_SECRET_KEY, ""),
        params={"created[gte]": since, "limit": 100},
        timeout=30
    )
    resp.raise_for_status()
    charges = resp.json().get("data", [])

    for charge in charges:
        if charge["status"] != "succeeded":
            continue
        amount_usd = charge["amount"] / 100.0
        # Attempt to map to a product via metadata
        product_id = charge.get("metadata", {}).get("product_id")
        if product_id:
            db.record_revenue(int(product_id), "stripe", amount_usd,
                              charge.get("currency", "usd").upper())

    log.info("Synced %d Stripe charges", len(charges))


# ─── GUMROAD REVENUE ─────────────────────────────────────────────────────────

def sync_gumroad_revenue():
    """Pull Gumroad sales and record them."""
    if not config.GUMROAD_ACCESS_TOKEN:
        return

    resp = requests.get(
        "https://api.gumroad.com/v2/sales",
        params={"access_token": config.GUMROAD_ACCESS_TOKEN},
        timeout=30
    )
    resp.raise_for_status()
    sales = resp.json().get("sales", [])

    for sale in sales:
        price = sale.get("price", 0) / 100.0
        product_permalink = sale.get("product_permalink", "")
        # Match by platform_id stored in products table
        with db.conn() as c:
            row = c.execute(
                "SELECT id FROM products WHERE platform='gumroad' AND platform_id=?",
                (sale.get("product_id"),)
            ).fetchone()
            if row:
                db.record_revenue(row["id"], "gumroad", price)

    log.info("Synced %d Gumroad sales", len(sales))


# ─── REPORTING ───────────────────────────────────────────────────────────────

def daily_report() -> dict:
    """Generate a daily P&L summary."""
    summary = db.revenue_summary()

    with db.conn() as c:
        total_products = c.execute(
            "SELECT COUNT(*) as n FROM products WHERE published_at IS NOT NULL"
        ).fetchone()["n"]

        top_products = c.execute(
            """SELECT title, type, platform, revenue_usd, units_sold
               FROM products ORDER BY revenue_usd DESC LIMIT 10"""
        ).fetchall()

        recent_jobs = c.execute(
            """SELECT pipeline, status, COUNT(*) as n
               FROM jobs GROUP BY pipeline, status"""
        ).fetchall()

    report = {
        "date": datetime.utcnow().isoformat(),
        "total_revenue_usd": summary["total_usd"],
        "revenue_by_source": summary["by_source"],
        "total_published_products": total_products,
        "top_products": [dict(r) for r in top_products],
        "job_status": [dict(r) for r in recent_jobs],
    }

    log.info(
        "Daily report: $%.2f total revenue across %d products",
        summary["total_usd"], total_products
    )
    return report


def sync_all_revenue():
    """Sync revenue from all configured platforms."""
    sync_stripe_revenue()
    sync_gumroad_revenue()
