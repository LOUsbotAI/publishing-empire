"""
Cloudflare Agent
================
Interfaces with the live Cloudflare Worker (silent-union-202e) + D1 database.

The Worker URL is set via CF_WORKER_URL in .env.
Admin requests use CF_ADMIN_KEY.
"""
import logging
import os
from datetime import datetime
from typing import Any

import requests

log = logging.getLogger("cf_agent")

WORKER_URL = os.getenv("CF_WORKER_URL", "").rstrip("/")
ADMIN_KEY  = os.getenv("ADMIN_KEY", "")


def _get(path: str, **params) -> dict:
    if not WORKER_URL:
        log.warning("CF_WORKER_URL not set — skipping CF sync")
        return {}
    url = f"{WORKER_URL}{path}"
    headers = {"X-Admin-Key": ADMIN_KEY} if ADMIN_KEY else {}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.error("CF Worker GET %s failed: %s", path, e)
        return {}


def health() -> dict:
    """Check the edge Worker is alive."""
    return _get("/health")


def list_books() -> list[dict]:
    """Return all ready-for-sale books from the edge catalogue."""
    data = _get("/books")
    return data.get("books", [])


def revenue_summary() -> dict:
    """Return live revenue totals from the edge."""
    return _get("/revenue")


def daily_revenue(days: int = 30) -> list[dict]:
    """Return last N days of daily revenue from the edge."""
    data = _get("/revenue/daily")
    return data.get("daily", [])


def milestones() -> list[dict]:
    """Return reached revenue milestones."""
    data = _get("/revenue/milestones")
    return data.get("milestones", [])


def sync_edge_revenue_to_local(db_conn) -> int:
    """
    Pull transactions recorded at the Cloudflare edge and write them
    into the local SQLite platform_sales table.
    Returns count of new rows inserted.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    import database as db

    data = revenue_summary()
    if not data:
        return 0

    by_currency = data.get("revenue_by_currency", [])
    inserted = 0
    for row in by_currency:
        try:
            with db.conn() as c:
                c.execute(
                    """INSERT OR IGNORE INTO platform_sales
                       (platform, platform_sale_id, amount_usd, currency,
                        product_name, customer_email, sale_date, notes)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        "cloudflare_edge",
                        f"cf_summary_{row.get('currency', 'aud')}",
                        round((row.get("total_cents", 0) / 100) * 0.64, 2),  # AUD→USD approx
                        row.get("currency", "AUD"),
                        "Edge Summary",
                        "",
                        datetime.utcnow().isoformat(),
                        f"transaction_count={row.get('transaction_count', 0)}",
                    )
                )
                inserted += 1
        except Exception as e:
            log.error("Failed to sync edge revenue row: %s", e)

    log.info("Synced %d edge revenue rows", inserted)
    return inserted


def log_milestone_reached(milestone: dict):
    """Log a milestone to local console + optionally notify."""
    notes = milestone.get("notes", "")
    reached = milestone.get("reached_at", "")
    log.info("MILESTONE REACHED: %s at %s", notes, reached)
