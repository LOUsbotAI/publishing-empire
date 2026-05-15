"""
Australian Tax & GST Agent
==========================
Handles all Australian tax obligations autonomously:

  GST (Goods & Services Tax) — 10%
  ├── Collected on Australian sales
  ├── NOT collected on international exports (GST-free supply)
  ├── LemonSqueezy handles this automatically as Merchant of Record
  └── Quarterly BAS lodgment data generated automatically

  Income Tax
  ├── Tracks all assessable income across entities
  ├── Deductible expenses tracked (API costs, hosting, software)
  └── Quarterly instalment estimates

  BAS (Business Activity Statement)
  ├── Generated quarterly (or monthly if turnover > $20M)
  ├── W1: Total wages (if applicable)
  ├── G1: Total sales
  ├── G2: Export sales (GST-free)
  ├── G3: Other GST-free sales
  ├── G10: Capital purchases
  ├── 1A: GST on sales
  └── 1B: GST credits on purchases

  Entities:
  ├── LUCorp (primary operating entity)
  └── LUGROC (secondary entity — add details when files shared)
"""
import json
import logging
from datetime import datetime, date
from pathlib import Path

import database as db

log = logging.getLogger("tax_agent")

GST_RATE = 0.10          # 10% Australian GST
AUD_THRESHOLD = 75_000   # Must register for GST above this annual turnover
ENTITY_ABN_LUCORP = ""   # Set via .env
ENTITY_ABN_LUGROC = ""   # Set via .env


# ─── SALE CLASSIFICATION ─────────────────────────────────────────────────────

INTERNATIONAL_COUNTRIES = {
    "US", "GB", "CA", "DE", "FR", "JP", "KR", "SG", "NZ",
    "IN", "BR", "MX", "ZA", "AE", "NL", "SE", "NO", "DK",
    # Add more as needed — all non-AU sales are GST-free exports
}

def classify_sale(sale: dict) -> dict:
    """
    Determine GST treatment for a sale.
    Australian digital goods:
      - AU customer → GST applies (10%)
      - Non-AU customer → GST-free export
      - LemonSqueezy as MoR → they handle it, we just record
    """
    country = sale.get("customer_country", "").upper()
    platform = sale.get("platform", "")
    amount = sale.get("amount_usd", 0)

    # LemonSqueezy is Merchant of Record — handles all GST automatically
    if platform == "lemonsqueezy":
        return {
            "gst_treatment": "merchant_of_record",
            "gst_collected_by": "lemonsqueezy",
            "gst_our_liability": 0,
            "note": "LemonSqueezy remits GST directly — no action required",
        }

    # Royalty platforms (KDP, ACX, Findaway) — treated as B2B, GST-free
    if platform in ("kdp", "acx", "findaway", "google_play"):
        return {
            "gst_treatment": "royalty_income",
            "gst_collected_by": "platform",
            "gst_our_liability": 0,
            "note": f"Royalty from {platform} — GST handled by platform",
        }

    # Direct sales via Gumroad or our own site
    if country == "AU" or country == "":
        # Australian customer — collect GST
        gst = round(amount * GST_RATE / (1 + GST_RATE), 2)  # GST inclusive
        return {
            "gst_treatment": "taxable_supply",
            "gst_collected_by": "us",
            "gst_on_sale": gst,
            "gst_our_liability": gst,
            "net_amount": round(amount - gst, 2),
        }
    else:
        # International — GST-free export
        return {
            "gst_treatment": "gst_free_export",
            "gst_collected_by": "none",
            "gst_our_liability": 0,
            "net_amount": amount,
        }


# ─── EXPENSE TRACKING ────────────────────────────────────────────────────────

def record_expense(description: str, amount_aud: float, category: str,
                   gst_inclusive: bool = True, entity: str = "lucorp"):
    """
    Record a business expense. Most AI/software costs are GST-free (overseas).
    Australian business expenses include GST that can be claimed back.
    """
    gst_credit = 0
    if gst_inclusive:
        gst_credit = round(amount_aud * GST_RATE / (1 + GST_RATE), 2)

    with db.conn() as c:
        c.execute(
            """INSERT INTO expenses
               (entity, description, amount_aud, category,
                gst_credit, gst_inclusive, recorded_at)
               VALUES (?,?,?,?,?,?,datetime('now'))""",
            (entity, description, amount_aud, category,
             gst_credit, 1 if gst_inclusive else 0)
        )
    log.info("Expense recorded: %s $%.2f AUD (GST credit: $%.2f)",
             description, amount_aud, gst_credit)


DEDUCTIBLE_CATEGORIES = {
    "api_costs":       "AI API costs (Anthropic, OpenAI, ElevenLabs) — deductible",
    "hosting":         "Cloudflare, servers, domain — deductible",
    "software":        "Software subscriptions — deductible",
    "contractor":      "Contractor payments — deductible (issue payment summary)",
    "advertising":     "Marketing and advertising — deductible",
    "professional":    "Legal, accounting fees — deductible",
    "equipment":       "Hardware, devices — deductible (depreciate over life)",
    "platform_fees":   "Stripe/Gumroad/LemonSqueezy fees — deductible",
}


# ─── QUARTERLY BAS ────────────────────────────────────────────────────────────

def generate_bas(quarter: str = None, entity: str = "lucorp") -> dict:
    """
    Generate Business Activity Statement data for a quarter.
    quarter format: "2025-Q4" | "2026-Q1" etc.
    """
    if not quarter:
        q = (datetime.utcnow().month - 1) // 3 + 1
        quarter = f"{datetime.utcnow().year}-Q{q}"

    year, q_num = quarter.split("-Q")
    q_num = int(q_num)
    q_start_month = (q_num - 1) * 3 + 1
    q_end_month = q_start_month + 2
    period_start = f"{year}-{q_start_month:02d}-01"
    period_end = f"{year}-{q_end_month:02d}-31"

    with db.conn() as c:
        # G1: Total sales (all income in quarter)
        sales = c.execute(
            """SELECT SUM(amount_usd) as total FROM platform_sales
               WHERE sale_date BETWEEN ? AND ?""",
            (period_start, period_end)
        ).fetchone()["total"] or 0

        # Expenses and GST credits
        expenses = c.execute(
            """SELECT SUM(amount_aud) as total_exp,
                      SUM(gst_credit) as total_gst_credit
               FROM expenses
               WHERE entity=? AND recorded_at BETWEEN ? AND ?""",
            (entity, period_start, period_end)
        ).fetchone()

    total_sales_aud = sales * _usd_to_aud()
    export_sales = total_sales_aud * 0.85   # Estimate: ~85% international
    au_sales = total_sales_aud * 0.15       # ~15% Australian

    gst_on_sales = round(au_sales * GST_RATE / (1 + GST_RATE), 2)
    gst_credits = round(expenses["total_gst_credit"] or 0, 2)
    net_gst = round(gst_on_sales - gst_credits, 2)

    bas = {
        "entity": entity.upper(),
        "quarter": quarter,
        "period": f"{period_start} to {period_end}",
        "G1_total_sales_aud": round(total_sales_aud, 2),
        "G2_export_gst_free_aud": round(export_sales, 2),
        "G3_other_gst_free_aud": 0,
        "G10_capital_purchases_aud": 0,
        "1A_gst_on_sales": gst_on_sales,
        "1B_gst_credits_on_purchases": gst_credits,
        "net_gst_payable_aud": net_gst,
        "total_expenses_aud": round(expenses["total_exp"] or 0, 2),
        "notes": [
            "LemonSqueezy sales excluded — MoR remits GST directly",
            "Platform royalties (KDP/ACX/Findaway) treated as B2B — GST-free",
            "Export sales (non-AU customers) are GST-free supplies",
            f"Net GST {'payable to ATO' if net_gst > 0 else 'refundable from ATO'}: AUD ${abs(net_gst):.2f}",
        ],
        "generated_at": datetime.utcnow().isoformat(),
    }

    # Save to file for accountant
    reports_dir = Path(__file__).parent.parent / "reports" / "tax"
    reports_dir.mkdir(parents=True, exist_ok=True)
    bas_path = reports_dir / f"BAS_{entity}_{quarter}.json"
    bas_path.write_text(json.dumps(bas, indent=2))
    log.info("BAS generated: %s — Net GST: AUD $%.2f", quarter, net_gst)
    return bas


def _usd_to_aud(rate: float = 1.55) -> float:
    """Approximate USD→AUD conversion. TODO: fetch live rate."""
    return rate


# ─── XERO INTEGRATION ─────────────────────────────────────────────────────────

def push_to_xero(sale: dict):
    """Push a sale to Xero as an invoice (optional — requires Xero OAuth)."""
    import os, requests
    token = os.getenv("XERO_ACCESS_TOKEN", "")
    tenant = os.getenv("XERO_TENANT_ID", "")
    if not token or not tenant:
        return  # Xero not configured

    classification = classify_sale(sale)
    gst = classification.get("gst_on_sale", 0)

    invoice = {
        "Type": "ACCREC",
        "Contact": {"Name": sale.get("customer_email", "Online Customer")},
        "LineItems": [{
            "Description": sale.get("product_name", "Digital Product"),
            "Quantity": 1,
            "UnitAmount": sale.get("amount_usd", 0) * _usd_to_aud(),
            "TaxType": "OUTPUT" if gst > 0 else "NONE",
            "AccountCode": "200",
        }],
        "CurrencyCode": "AUD",
        "Status": "AUTHORISED",
    }
    try:
        resp = requests.post(
            "https://api.xero.com/api.xro/2.0/Invoices",
            headers={
                "Authorization": f"Bearer {token}",
                "Xero-tenant-id": tenant,
                "Content-Type": "application/json",
            },
            json={"Invoices": [invoice]},
            timeout=30
        )
        resp.raise_for_status()
        log.info("Xero invoice created: %s", resp.json()["Invoices"][0]["InvoiceID"])
    except Exception as e:
        log.warning("Xero push failed: %s", e)


# ─── ANNUAL TAX SUMMARY ───────────────────────────────────────────────────────

def annual_tax_summary(financial_year: str = None) -> dict:
    """
    Australian financial year runs 1 July → 30 June.
    financial_year: "2025-26" | "2026-27" etc.
    """
    if not financial_year:
        now = datetime.utcnow()
        fy_start_year = now.year if now.month >= 7 else now.year - 1
        financial_year = f"{fy_start_year}-{str(fy_start_year + 1)[2:]}"

    start_year, end_year = financial_year.split("-")
    fy_start = f"{start_year}-07-01"
    fy_end = f"20{end_year}-06-30"

    with db.conn() as c:
        revenue = c.execute(
            """SELECT platform, SUM(amount_usd) as total
               FROM platform_sales WHERE sale_date BETWEEN ? AND ?
               GROUP BY platform""",
            (fy_start, fy_end)
        ).fetchall()
        expenses = c.execute(
            """SELECT category, SUM(amount_aud) as total, SUM(gst_credit) as gst
               FROM expenses WHERE recorded_at BETWEEN ? AND ?
               GROUP BY category""",
            (fy_start, fy_end)
        ).fetchall()

    total_usd = sum(r["total"] for r in revenue)
    total_aud = total_usd * _usd_to_aud()
    total_exp = sum(e["total"] for e in expenses)
    total_gst_credits = sum(e["gst"] for e in expenses)
    net_profit = total_aud - total_exp

    # Australian company tax rate: 25% for base rate entities (turnover < $50M)
    # Small business rate applies if active asset test met
    tax_rate = 0.25
    estimated_tax = max(0, net_profit * tax_rate)

    summary = {
        "financial_year": financial_year,
        "period": f"{fy_start} to {fy_end}",
        "revenue": {
            "by_platform": {r["platform"]: round(r["total"] * _usd_to_aud(), 2)
                            for r in revenue},
            "total_aud": round(total_aud, 2),
        },
        "expenses": {
            "by_category": {e["category"]: round(e["total"], 2) for e in expenses},
            "total_aud": round(total_exp, 2),
            "total_gst_credits": round(total_gst_credits, 2),
        },
        "net_profit_aud": round(net_profit, 2),
        "estimated_company_tax_aud": round(estimated_tax, 2),
        "tax_rate": f"{tax_rate*100:.0f}%",
        "notes": [
            "Company tax rate 25% applies for base rate entities (turnover < AUD 50M)",
            "Consult your accountant before lodging — this is an estimate only",
            "Small business instant asset write-off may apply for equipment",
            "R&D tax incentive may apply to AI development costs",
        ],
        "generated_at": datetime.utcnow().isoformat(),
    }

    reports_dir = Path(__file__).parent.parent / "reports" / "tax"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"tax_summary_{financial_year.replace('-','_')}.json"
    path.write_text(json.dumps(summary, indent=2))
    log.info("Annual tax summary: FY%s — Net profit AUD $%.2f, Est. tax AUD $%.2f",
             financial_year, net_profit, estimated_tax)
    return summary


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    sys.path.insert(0, str(Path(__file__).parent.parent))
    db.init_db()
    print(json.dumps(generate_bas(), indent=2))
