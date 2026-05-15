"""
Publishing Empire Storefront
FastAPI web server — serves the store, handles Stripe checkout and webhooks.
"""
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Allow imports from parent package
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
import database as db
from agents import stripe_agent

log = logging.getLogger(__name__)

app = FastAPI(title="Publishing Empire", docs_url=None, redoc_url=None)

BASE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))

LANG_NAMES = {
    "en": "English", "es": "Spanish", "pt": "Portuguese",
    "de": "German", "fr": "French", "it": "Italian",
    "ja": "Japanese", "zh": "Chinese", "ko": "Korean", "ar": "Arabic",
}

WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _get_products(type_filter: str = None, limit: int = 100) -> list[dict]:
    with db.conn() as c:
        query = """
            SELECT p.id, p.title, p.type, p.language, p.price_usd,
                   p.platform_url, j.niche, p.meta
            FROM products p
            LEFT JOIN jobs j ON p.job_id = j.id
            WHERE p.published_at IS NOT NULL AND p.price_usd > 0
        """
        args = []
        if type_filter:
            if type_filter == "video":
                query += " AND p.type IN ('video_long','video_short')"
            else:
                query += " AND p.type = ?"
                args.append(type_filter)
        query += " ORDER BY p.published_at DESC LIMIT ?"
        args.append(limit)
        rows = c.execute(query, args).fetchall()

    products = []
    for row in rows:
        meta = json.loads(row["meta"] or "{}")
        products.append({
            "id": row["id"],
            "title": row["title"],
            "type": row["type"],
            "language": row["language"],
            "price_usd": row["price_usd"] or 9.99,
            "niche": row["niche"],
            "description": meta.get("back_cover_blurb", ""),
            "subtitle": meta.get("subtitle", ""),
            "keywords": meta.get("keywords", []),
            "cover_url": None,  # extend: serve from /static/covers/{id}.jpg
        })
    return products


def _get_product(product_id: int) -> dict | None:
    with db.conn() as c:
        row = c.execute(
            """SELECT p.*, j.niche FROM products p
               LEFT JOIN jobs j ON p.job_id = j.id WHERE p.id = ?""",
            (product_id,)
        ).fetchone()
    if not row:
        return None
    meta = json.loads(row["meta"] or "{}")
    return {
        "id": row["id"],
        "title": row["title"],
        "type": row["type"],
        "language": row["language"],
        "price_usd": row["price_usd"] or 9.99,
        "file_path": row["file_path"],
        "niche": row["niche"],
        "description": meta.get("back_cover_blurb", ""),
        "subtitle": meta.get("subtitle", ""),
        "keywords": meta.get("keywords", []),
        "cover_url": None,
    }


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    db.init_db()
    products = _get_products(limit=6)
    with db.conn() as c:
        total = c.execute("SELECT COUNT(*) as n FROM products WHERE published_at IS NOT NULL").fetchone()["n"]
        langs = c.execute("SELECT DISTINCT language FROM products WHERE published_at IS NOT NULL").fetchall()
        niches = c.execute("SELECT DISTINCT niche FROM jobs").fetchall()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "products": products,
        "total_products": total,
        "total_languages": len(langs),
        "total_niches": len(niches),
    })


@app.get("/store", response_class=HTMLResponse)
async def store(request: Request, type: Optional[str] = None):
    db.init_db()
    products = _get_products(type_filter=type)
    all_languages = list({p["language"] for p in products})
    all_languages.sort()

    products_by_lang = {}
    for lang in all_languages:
        products_by_lang[lang] = [p for p in products if p["language"] == lang]

    return templates.TemplateResponse("store.html", {
        "request": request,
        "products_by_lang": products_by_lang,
        "languages": all_languages,
        "lang_names": LANG_NAMES,
        "total": len(products),
        "active_type": type,
    })


@app.get("/product/{product_id}", response_class=HTMLResponse)
async def product_page(request: Request, product_id: int):
    db.init_db()
    product = _get_product(product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    return templates.TemplateResponse("product.html", {
        "request": request,
        "product": product,
        "lang_names": LANG_NAMES,
    })


@app.post("/checkout/{product_id}")
async def checkout(request: Request, product_id: int):
    """Create a Stripe checkout session and redirect."""
    db.init_db()
    product = _get_product(product_id)
    if not product:
        raise HTTPException(404, "Product not found")

    base_url = str(request.base_url).rstrip("/")
    try:
        checkout_url = stripe_agent.create_checkout_session(
            product_id=product_id,
            success_url=f"{base_url}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base_url}/product/{product_id}",
        )
        return RedirectResponse(checkout_url, status_code=303)
    except Exception as e:
        log.error("Checkout failed for product %d: %s", product_id, e)
        raise HTTPException(500, "Checkout unavailable — please try again")


@app.get("/success", response_class=HTMLResponse)
async def success_page(request: Request, session_id: str):
    """Post-payment page — issue download token."""
    db.init_db()
    with db.conn() as c:
        row = c.execute(
            "SELECT download_token, product_id, customer_email FROM orders WHERE stripe_session_id=?",
            (session_id,)
        ).fetchone()

    if row and row["download_token"]:
        product = _get_product(row["product_id"])
        return templates.TemplateResponse("success.html", {
            "request": request,
            "token": row["download_token"],
            "title": product["title"] if product else "Your Purchase",
            "type": product["type"] if product else "",
            "lang": LANG_NAMES.get(product["language"], "") if product else "",
        })

    # Stripe will POST to /webhook, which creates the token — poll briefly
    return HTMLResponse("""
    <html><head><meta http-equiv="refresh" content="3;url=/success?session_id=""" + session_id + """">
    </head><body style="background:#08080f;color:#e8e6f0;font-family:Inter,sans-serif;
    display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center;">
    <div><div style="font-size:3rem;margin-bottom:1rem">⏳</div>
    <h2>Confirming your payment…</h2><p style="color:#8884a0">This takes just a moment.</p>
    </div></body></html>
    """)


@app.get("/download/{token}")
async def download(token: str):
    """Serve the purchased file via a secure one-time token."""
    db.init_db()
    info = stripe_agent.validate_download_token(token)
    if not info:
        raise HTTPException(410, "This download link has expired or already been used.")

    file_path = Path(info["file_path"]) if info.get("file_path") else None
    if not file_path or not file_path.exists():
        raise HTTPException(404, "File not found — please contact support.")

    stripe_agent.mark_token_used(token)
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/octet-stream",
    )


@app.post("/webhook/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None)
):
    """Receive and verify Stripe webhook events."""
    payload = await request.body()

    if WEBHOOK_SECRET and stripe_signature:
        try:
            event = stripe_agent.verify_webhook(payload, stripe_signature, WEBHOOK_SECRET)
        except ValueError as e:
            log.warning("Invalid webhook: %s", e)
            raise HTTPException(400, str(e))
    else:
        event = json.loads(payload)

    result = stripe_agent.handle_webhook_event(event)

    # If checkout completed, store the order + token
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        product_id = session.get("metadata", {}).get("product_id")
        email = session.get("customer_details", {}).get("email", "")
        amount = session.get("amount_total", 0) / 100.0

        if product_id:
            import secrets
            from datetime import datetime, timedelta
            token = secrets.token_urlsafe(32)
            expires = (datetime.utcnow() + timedelta(hours=48)).isoformat()

            with db.conn() as c:
                c.execute(
                    """INSERT OR IGNORE INTO download_tokens
                       (token, product_id, customer_email, expires_at, used)
                       VALUES (?,?,?,?,0)""",
                    (token, int(product_id), email, expires)
                )
                c.execute(
                    """INSERT OR IGNORE INTO orders
                       (stripe_session_id, product_id, customer_email, amount_usd, status, download_token)
                       VALUES (?,?,?,?,'paid',?)""",
                    (session["id"], int(product_id), email, amount, token)
                )

    return JSONResponse({"status": "ok"})


@app.get("/admin/report")
async def admin_report(request: Request, key: str = ""):
    admin_key = os.getenv("ADMIN_KEY", "")
    if admin_key and key != admin_key:
        raise HTTPException(403, "Forbidden")
    db.init_db()
    from agents import payout_agent
    report = {
        "transactions": stripe_agent.transaction_monitor_report(),
        "financials": payout_agent.full_financial_status(),
    }
    return JSONResponse(report)


@app.post("/admin/payout")
async def admin_payout(request: Request, key: str = ""):
    """Manually trigger a payout — protected endpoint."""
    admin_key = os.getenv("ADMIN_KEY", "")
    if admin_key and key != admin_key:
        raise HTTPException(403, "Forbidden")
    from agents import payout_agent
    result = payout_agent.trigger_payout()
    return JSONResponse(result)


@app.get("/terms", response_class=HTMLResponse)
async def terms(request: Request):
    return templates.TemplateResponse("legal.html", {
        "request": request,
        "page_title": "Terms of Service",
        "last_updated": "2025",
        "body": """
        <h2>1. Digital Products</h2>
        <p>Publishing Empire sells digital content including audiobooks, ebooks, and video courses.
        All products are delivered electronically via a secure download link valid for 48 hours after purchase.</p>

        <h2>2. Payment</h2>
        <p>All payments are processed securely by Stripe. We accept all major credit and debit cards.
        Prices are in USD. Your card is charged immediately upon purchase.</p>

        <h2>3. Refund Policy</h2>
        <p>Due to the digital nature of our products, all sales are final once the download link has been accessed.
        If you have not yet downloaded your file and experience a technical issue, contact us within 24 hours.</p>

        <h2>4. International Sales</h2>
        <p>We sell internationally. You are responsible for any applicable taxes or import duties in your jurisdiction.
        Content is available in multiple languages as described on each product page.</p>

        <h2>5. Intellectual Property</h2>
        <p>All content sold through this store is for personal use only. Redistribution, resale, or reproduction
        in any form is prohibited without written permission.</p>

        <h2>6. Contact</h2>
        <p>For support, email us at support@publishingempire.com</p>
        """
    })


@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse("legal.html", {
        "request": request,
        "page_title": "Privacy Policy",
        "last_updated": "2025",
        "body": """
        <h2>What We Collect</h2>
        <p>When you make a purchase, Stripe collects your payment information. We receive only your email address
        and order details — we never see or store your card number.</p>

        <h2>How We Use It</h2>
        <ul>
          <li>To deliver your purchased download</li>
          <li>To send purchase confirmation emails</li>
          <li>To notify you of new content in categories you've purchased from</li>
        </ul>

        <h2>Third Parties</h2>
        <p>We use Stripe for payment processing (stripe.com/privacy) and Mailchimp for email (mailchimp.com/privacy).
        We do not sell your data to any other third parties.</p>

        <h2>Data Retention</h2>
        <p>Order records are retained for 7 years for tax and accounting purposes.
        You may request deletion of your personal data at any time by emailing us.</p>

        <h2>Cookies</h2>
        <p>This site uses only essential session cookies required for the checkout process. No tracking cookies.</p>
        """
    })


# ─── RUN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    db.init_db()
    stripe_agent.sync_all_products_to_stripe()
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
