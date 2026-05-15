"""
Termux Bridge
=============
Connects this system to the existing Lousta Books Node.js system
running in Termux on the phone (/root/publishing-empire-live/).

Two-way sync:
  Termux Node.js → sends sales events → this system records them
  This system → sends new book jobs → Termux picks them up

Run this alongside the main orchestrator.
The Node.js system should POST to http://localhost:8001/
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

import sys
sys.path.insert(0, str(Path(__file__).parent))
import database as db
from agents import tax_agent

log = logging.getLogger("termux_bridge")
BRIDGE_KEY = os.getenv("BRIDGE_API_KEY", "change_this_bridge_key")

app = FastAPI(title="Termux Bridge", docs_url=None)


def _auth(request: Request):
    key = request.headers.get("X-Bridge-Key", "")
    if key != BRIDGE_KEY:
        raise HTTPException(403, "Invalid bridge key")


# ── INBOUND: Node.js system → this system ────────────────────────────────────

@app.post("/bridge/sale")
async def receive_sale(request: Request):
    """Node.js Stripe sale → recorded here with GST classification."""
    _auth(request)
    sale = await request.json()

    # Classify for Australian GST
    classification = tax_agent.classify_sale(sale)

    with db.conn() as c:
        c.execute(
            """INSERT OR IGNORE INTO platform_sales
               (platform, platform_sale_id, amount_usd, currency,
                product_name, customer_email, sale_date, notes)
               VALUES (?,?,?,?,?,?,?,?)""",
            ("stripe_termux",
             sale.get("charge_id", f"manual_{datetime.utcnow().isoformat()}"),
             sale.get("amount_usd", 0),
             sale.get("currency", "USD"),
             sale.get("product_name", ""),
             sale.get("customer_email", ""),
             sale.get("created", datetime.utcnow().isoformat()),
             json.dumps(classification))
        )

    log.info("Sale received from Termux: $%.2f — GST: %s",
             sale.get("amount_usd", 0), classification.get("gst_treatment"))
    return JSONResponse({"status": "recorded", "gst": classification})


@app.post("/bridge/batch_sales")
async def receive_batch_sales(request: Request):
    """Bulk import sales from the Node.js system (e.g. CSV export sync)."""
    _auth(request)
    body = await request.json()
    sales = body.get("sales", [])
    recorded = 0
    for sale in sales:
        with db.conn() as c:
            try:
                classification = tax_agent.classify_sale(sale)
                c.execute(
                    """INSERT OR IGNORE INTO platform_sales
                       (platform, platform_sale_id, amount_usd, currency,
                        product_name, customer_email, sale_date, notes)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    ("stripe_termux",
                     sale.get("id", ""),
                     sale.get("amount_usd", 0),
                     sale.get("currency", "USD"),
                     sale.get("description", ""),
                     sale.get("customer_email", ""),
                     sale.get("created", ""),
                     json.dumps(classification))
                )
                recorded += 1
            except Exception:
                pass
    log.info("Batch import: %d/%d sales recorded", recorded, len(sales))
    return JSONResponse({"status": "ok", "recorded": recorded, "total": len(sales)})


@app.post("/bridge/expense")
async def receive_expense(request: Request):
    """Record a business expense from the Node.js system."""
    _auth(request)
    exp = await request.json()
    tax_agent.record_expense(
        description=exp.get("description", ""),
        amount_aud=exp.get("amount_aud", 0),
        category=exp.get("category", "other"),
        gst_inclusive=exp.get("gst_inclusive", False),
        entity=exp.get("entity", "lucorp"),
    )
    return JSONResponse({"status": "recorded"})


# ── OUTBOUND: this system → Node.js system ────────────────────────────────────

@app.get("/bridge/pending_jobs")
async def get_pending_jobs(request: Request):
    """Node.js system polls this to pick up new content jobs."""
    _auth(request)
    jobs = db.get_pending_jobs()
    return JSONResponse({"jobs": jobs[:10]})


@app.get("/bridge/revenue")
async def get_revenue(request: Request):
    """Unified revenue across ALL platforms — for the Node.js dashboard."""
    _auth(request)
    summary = db.revenue_summary()
    with db.conn() as c:
        by_platform = c.execute(
            """SELECT platform, SUM(amount_usd) as total, COUNT(*) as sales
               FROM platform_sales GROUP BY platform ORDER BY total DESC"""
        ).fetchall()
    return JSONResponse({
        "all_time_usd": summary["total_usd"],
        "by_source": summary["by_source"],
        "by_platform": [dict(r) for r in by_platform],
        "timestamp": datetime.utcnow().isoformat(),
    })


@app.get("/bridge/bas/{quarter}")
async def get_bas(request: Request, quarter: str):
    """Return BAS data for a given quarter — e.g. /bridge/bas/2026-Q1"""
    _auth(request)
    bas = tax_agent.generate_bas(quarter)
    return JSONResponse(bas)


@app.get("/bridge/tax/annual")
async def get_annual_tax(request: Request, fy: str = None):
    _auth(request)
    summary = tax_agent.annual_tax_summary(fy)
    return JSONResponse(summary)


@app.get("/bridge/health")
async def health(request: Request):
    return JSONResponse({"status": "ok", "service": "termux_bridge",
                         "timestamp": datetime.utcnow().isoformat()})


# ── INSTRUCTIONS for Node.js side ────────────────────────────────────────────
#
# Add this to your publishing-empire-live/server-production.js:
#
# const BRIDGE_URL = 'http://localhost:8001';
# const BRIDGE_KEY = process.env.BRIDGE_API_KEY;
#
# // After a successful Stripe payment:
# async function notifyBridge(charge) {
#   await fetch(`${BRIDGE_URL}/bridge/sale`, {
#     method: 'POST',
#     headers: { 'Content-Type': 'application/json', 'X-Bridge-Key': BRIDGE_KEY },
#     body: JSON.stringify({
#       charge_id: charge.id,
#       amount_usd: charge.amount / 100,
#       currency: charge.currency,
#       customer_email: charge.billing_details?.email || '',
#       description: charge.description || 'LOUSTA Transaction',
#       created: new Date(charge.created * 1000).toISOString(),
#     })
#   }).catch(e => console.log('Bridge notification failed (non-critical):', e));
# }

if __name__ == "__main__":
    db.init_db()
    port = int(os.getenv("BRIDGE_PORT", "8001"))
    log.info("Termux Bridge starting on port %d", port)
    uvicorn.run(app, host="127.0.0.1", port=port)
