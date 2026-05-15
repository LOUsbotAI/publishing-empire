"""
Revenue Aggregator
==================
Watches every platform's sales and royalties.
Each platform pays your bank directly — this agent just tracks it all.

Platform payout schedules:
  Amazon KDP      → bank, monthly (60 days after month end)
  ACX / Audible   → bank, monthly
  Google Play     → bank, monthly (when >$10 threshold)
  Gumroad         → bank, weekly (Friday)
  Findaway Voices → bank, monthly
  LemonSqueezy    → bank, weekly (configurable)
"""
import csv
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import requests
import config
import database as db

log = logging.getLogger("revenue_aggregator")


# ─── GUMROAD ─────────────────────────────────────────────────────────────────
# Gumroad pays directly to your bank (Settings → Payouts → Add bank account)
# API gives us real-time sales data

def sync_gumroad() -> dict:
    token = config.GUMROAD_ACCESS_TOKEN
    if not token:
        return {"platform": "gumroad", "status": "not_configured"}

    resp = requests.get(
        "https://api.gumroad.com/v2/sales",
        params={"access_token": token},
        timeout=30
    )
    resp.raise_for_status()
    sales = resp.json().get("sales", [])

    total = 0.0
    new_count = 0
    for sale in sales:
        amount = sale.get("price", 0) / 100.0
        sale_id = sale.get("id")
        with db.conn() as c:
            exists = c.execute(
                "SELECT id FROM platform_sales WHERE platform_sale_id=?", (sale_id,)
            ).fetchone()
            if not exists:
                c.execute(
                    """INSERT INTO platform_sales
                       (platform, platform_sale_id, amount_usd, currency,
                        product_name, customer_email, sale_date)
                       VALUES (?,?,?,?,?,?,?)""",
                    ("gumroad", sale_id, amount, "USD",
                     sale.get("product_name", ""),
                     sale.get("email", ""),
                     sale.get("created_at", ""))
                )
                total += amount
                new_count += 1

    log.info("Gumroad: +%d new sales, +$%.2f", new_count, total)
    return {"platform": "gumroad", "new_sales": new_count, "new_revenue_usd": total}


# ─── LEMONSQUEEZY ─────────────────────────────────────────────────────────────
# LemonSqueezy is Merchant of Record — handles all global tax automatically.
# They pay weekly to your bank. No Stripe needed.

def sync_lemonsqueezy() -> dict:
    api_key = os.getenv("LEMONSQUEEZY_API_KEY", "")
    if not api_key:
        return {"platform": "lemonsqueezy", "status": "not_configured"}

    resp = requests.get(
        "https://api.lemonsqueezy.com/v1/orders",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/vnd.api+json",
        },
        timeout=30
    )
    resp.raise_for_status()
    orders = resp.json().get("data", [])

    total = 0.0
    new_count = 0
    for order in orders:
        attrs = order.get("attributes", {})
        if attrs.get("status") != "paid":
            continue
        order_id = order["id"]
        amount = attrs.get("total", 0) / 100.0

        with db.conn() as c:
            exists = c.execute(
                "SELECT id FROM platform_sales WHERE platform_sale_id=?",
                (f"ls_{order_id}",)
            ).fetchone()
            if not exists:
                c.execute(
                    """INSERT INTO platform_sales
                       (platform, platform_sale_id, amount_usd, currency,
                        product_name, customer_email, sale_date)
                       VALUES (?,?,?,?,?,?,?)""",
                    ("lemonsqueezy", f"ls_{order_id}", amount,
                     attrs.get("currency", "USD"),
                     attrs.get("first_order_item", {}).get("product_name", ""),
                     attrs.get("user_email", ""),
                     attrs.get("created_at", ""))
                )
                total += amount
                new_count += 1

    log.info("LemonSqueezy: +%d new orders, +$%.2f", new_count, total)
    return {"platform": "lemonsqueezy", "new_sales": new_count, "new_revenue_usd": total}


# ─── AMAZON KDP ───────────────────────────────────────────────────────────────
# KDP has no public API — royalties deposited directly to your bank monthly.
# We import from KDP CSV reports (download from KDP Reports tab).

def import_kdp_csv(csv_path: Path) -> dict:
    """Import a KDP royalty report CSV downloaded from kdp.amazon.com."""
    if not csv_path.exists():
        return {"platform": "kdp", "status": "no_file"}

    total = 0.0
    rows = 0
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # KDP CSV columns vary by report type — handle common formats
            royalty = float(row.get("Royalty", row.get("Net Royalty", "0")).replace(",", "") or 0)
            if royalty <= 0:
                continue
            asin = row.get("ASIN", row.get("Product", f"row_{rows}"))
            period = row.get("Royalty Payment Date", row.get("Month", ""))
            with db.conn() as c:
                exists = c.execute(
                    "SELECT id FROM platform_sales WHERE platform_sale_id=?",
                    (f"kdp_{asin}_{period}",)
                ).fetchone()
                if not exists:
                    c.execute(
                        """INSERT INTO platform_sales
                           (platform, platform_sale_id, amount_usd, currency,
                            product_name, sale_date)
                           VALUES (?,?,?,?,?,?)""",
                        ("kdp", f"kdp_{asin}_{period}", royalty,
                         row.get("Currency", "USD"),
                         row.get("Title", asin), period)
                    )
                    total += royalty
                    rows += 1

    log.info("KDP CSV imported: %d royalty records, $%.2f total", rows, total)
    return {"platform": "kdp", "imported_rows": rows, "total_royalties_usd": total}


# ─── ACX / AUDIBLE ────────────────────────────────────────────────────────────
# ACX pays directly to your bank monthly. Download CSV from acx.com → Reports.

def import_acx_csv(csv_path: Path) -> dict:
    if not csv_path.exists():
        return {"platform": "acx", "status": "no_file"}

    total = 0.0
    rows = 0
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            royalty = float(row.get("Royalty", row.get("Amount", "0")).replace(",", "") or 0)
            if royalty <= 0:
                continue
            record_id = row.get("Title", "") + row.get("Period", "")
            with db.conn() as c:
                exists = c.execute(
                    "SELECT id FROM platform_sales WHERE platform_sale_id=?",
                    (f"acx_{record_id}",)
                ).fetchone()
                if not exists:
                    c.execute(
                        """INSERT INTO platform_sales
                           (platform, platform_sale_id, amount_usd, currency,
                            product_name, sale_date)
                           VALUES (?,?,?,?,?,?)""",
                        ("acx", f"acx_{record_id}", royalty, "USD",
                         row.get("Title", ""), row.get("Period", ""))
                    )
                    total += royalty
                    rows += 1

    log.info("ACX CSV imported: %d records, $%.2f", rows, total)
    return {"platform": "acx", "imported_rows": rows, "total_royalties_usd": total}


# ─── GOOGLE PLAY BOOKS ────────────────────────────────────────────────────────
# Google pays monthly to bank via AdSense/Partner payments.
# Download CSV from play.google.com/books/publish → Reports.

def import_google_play_csv(csv_path: Path) -> dict:
    if not csv_path.exists():
        return {"platform": "google_play", "status": "no_file"}

    total = 0.0
    rows = 0
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            amount = float(
                row.get("Amount (USD)", row.get("Estimated Earnings", "0"))
                .replace(",", "").replace("$", "") or 0
            )
            if amount <= 0:
                continue
            record_id = row.get("Book ID", "") + row.get("Month", "")
            with db.conn() as c:
                exists = c.execute(
                    "SELECT id FROM platform_sales WHERE platform_sale_id=?",
                    (f"gplay_{record_id}",)
                ).fetchone()
                if not exists:
                    c.execute(
                        """INSERT INTO platform_sales
                           (platform, platform_sale_id, amount_usd, currency,
                            product_name, sale_date)
                           VALUES (?,?,?,?,?,?)""",
                        ("google_play", f"gplay_{record_id}", amount, "USD",
                         row.get("Title", ""), row.get("Month", ""))
                    )
                    total += amount
                    rows += 1

    log.info("Google Play CSV imported: %d records, $%.2f", rows, total)
    return {"platform": "google_play", "imported_rows": rows, "total_royalties_usd": total}


# ─── FINDAWAY VOICES ──────────────────────────────────────────────────────────
# Findaway distributes to Spotify, Apple Books, Kobo, Scribd, etc.
# Pays monthly to bank. Import their CSV reports.

def import_findaway_csv(csv_path: Path) -> dict:
    if not csv_path.exists():
        return {"platform": "findaway", "status": "no_file"}

    total = 0.0
    rows = 0
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            amount = float(row.get("Net Revenue", row.get("Revenue", "0")).replace(",", "") or 0)
            if amount <= 0:
                continue
            record_id = row.get("Title", "") + row.get("Period", "") + row.get("Retailer", "")
            with db.conn() as c:
                exists = c.execute(
                    "SELECT id FROM platform_sales WHERE platform_sale_id=?",
                    (f"findaway_{record_id}",)
                ).fetchone()
                if not exists:
                    c.execute(
                        """INSERT INTO platform_sales
                           (platform, platform_sale_id, amount_usd, currency,
                            product_name, sale_date, notes)
                           VALUES (?,?,?,?,?,?,?)""",
                        ("findaway", f"findaway_{record_id}", amount, "USD",
                         row.get("Title", ""), row.get("Period", ""),
                         row.get("Retailer", ""))
                    )
                    total += amount
                    rows += 1

    log.info("Findaway CSV imported: %d records, $%.2f", rows, total)
    return {"platform": "findaway", "imported_rows": rows, "total_royalties_usd": total}


# ─── AUTO-IMPORT from a watched folder ───────────────────────────────────────

REPORTS_DIR = config.BASE_DIR / "reports"

def watch_and_import_reports():
    """
    Scan the reports/ folder for new CSVs and auto-import them.
    Drop any platform CSV into reports/ and it's picked up automatically.
    Naming convention:
      kdp_*.csv, acx_*.csv, google_play_*.csv, findaway_*.csv
    """
    REPORTS_DIR.mkdir(exist_ok=True)
    results = []
    for csv_file in REPORTS_DIR.glob("*.csv"):
        name = csv_file.name.lower()
        if name.startswith("kdp"):
            results.append(import_kdp_csv(csv_file))
        elif name.startswith("acx"):
            results.append(import_acx_csv(csv_file))
        elif name.startswith("google_play") or name.startswith("gplay"):
            results.append(import_google_play_csv(csv_file))
        elif name.startswith("findaway"):
            results.append(import_findaway_csv(csv_file))
        # Move processed file to avoid re-importing
        done_dir = REPORTS_DIR / "processed"
        done_dir.mkdir(exist_ok=True)
        csv_file.rename(done_dir / csv_file.name)
    return results


# ─── UNIFIED REVENUE SUMMARY ─────────────────────────────────────────────────

def sync_cloudflare_edge() -> dict:
    """Pull revenue from the live Cloudflare edge Worker."""
    try:
        from agents import cloudflare_agent
        data = cloudflare_agent.revenue_summary()
        if not data:
            return {"platform": "cloudflare_edge", "status": "no_data"}
        by_currency = data.get("revenue_by_currency", [])
        total_usd = 0.0
        for row in by_currency:
            cents = row.get("total_cents", 0) or 0
            currency = (row.get("currency") or "aud").upper()
            if currency == "AUD":
                total_usd += cents / 100 * 0.64
            else:
                total_usd += cents / 100
        log.info("CF edge revenue: %d currency rows, ~$%.2f USD", len(by_currency), total_usd)
        return {
            "platform": "cloudflare_edge",
            "total_usd": round(total_usd, 2),
            "by_currency": by_currency,
            "customers": data.get("total_customers", 0),
            "milestones": len(data.get("milestones", [])),
        }
    except Exception as e:
        log.error("CF edge sync failed: %s", e)
        return {"platform": "cloudflare_edge", "status": "error", "error": str(e)}


def full_revenue_report() -> dict:
    """Aggregate revenue from every source — APIs + imported CSVs."""
    # Sync live API platforms
    api_results = []
    if config.GUMROAD_ACCESS_TOKEN:
        api_results.append(sync_gumroad())
    if os.getenv("LEMONSQUEEZY_API_KEY"):
        api_results.append(sync_lemonsqueezy())
    if os.getenv("CF_WORKER_URL"):
        api_results.append(sync_cloudflare_edge())

    # Import any CSV reports dropped in reports/
    csv_results = watch_and_import_reports()

    # Query totals from DB
    with db.conn() as c:
        by_platform = c.execute(
            """SELECT platform,
                      SUM(amount_usd) as total,
                      COUNT(*) as sales
               FROM platform_sales
               GROUP BY platform
               ORDER BY total DESC"""
        ).fetchall()

        grand_total = c.execute(
            "SELECT SUM(amount_usd) as total FROM platform_sales"
        ).fetchone()["total"] or 0

        this_month = c.execute(
            """SELECT SUM(amount_usd) as total FROM platform_sales
               WHERE sale_date >= date('now','start of month')"""
        ).fetchone()["total"] or 0

    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "grand_total_all_platforms_usd": grand_total,
        "this_month_usd": this_month,
        "by_platform": [
            {"platform": r["platform"], "total_usd": r["total"], "sales": r["sales"]}
            for r in by_platform
        ],
        "api_synced": api_results,
        "csv_imported": csv_results,
    }

    log.info(
        "Revenue summary: $%.2f all-time | $%.2f this month | %d platforms",
        grand_total, this_month, len(by_platform)
    )
    return report


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    sys.path.insert(0, str(Path(__file__).parent.parent))
    db.init_db()
    import json as _json
    print(_json.dumps(full_revenue_report(), indent=2))
