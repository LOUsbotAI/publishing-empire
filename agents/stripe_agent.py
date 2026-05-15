"""
Stripe Payment Agent
====================
Fully autonomous transaction lifecycle:
- Creates Stripe products/prices when new content is published
- Handles incoming webhooks (payment confirmed → deliver download)
- Monitors all revenue in real time
- Issues refunds if needed
- Syncs payout schedules
- Sends daily transaction summaries
"""
import hashlib
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
import config
import database as db

log = logging.getLogger(__name__)

STRIPE_BASE = "https://api.stripe.com/v1"


def _stripe(method: str, endpoint: str, data: dict = None, params: dict = None):
    """Make an authenticated Stripe API call."""
    url = f"{STRIPE_BASE}/{endpoint}"
    auth = (config.STRIPE_SECRET_KEY, "")
    if method == "GET":
        resp = requests.get(url, auth=auth, params=params or {}, timeout=30)
    elif method == "POST":
        resp = requests.post(url, auth=auth, data=data or {}, timeout=30)
    elif method == "DELETE":
        resp = requests.delete(url, auth=auth, timeout=30)
    else:
        raise ValueError(f"Unknown method: {method}")
    resp.raise_for_status()
    return resp.json()


# ─── PRODUCT SYNC ─────────────────────────────────────────────────────────────

def create_stripe_product(product_id: int, title: str, description: str,
                           price_usd: float, product_type: str,
                           cover_url: str = None) -> dict:
    """Create a Stripe product + price for a newly published item."""
    # Create product
    product_data = {
        "name": title[:250],
        "description": description[:500] if description else "",
        "metadata[product_id]": str(product_id),
        "metadata[type]": product_type,
    }
    if cover_url:
        product_data["images[]"] = cover_url

    stripe_product = _stripe("POST", "products", product_data)

    # Create price
    stripe_price = _stripe("POST", "prices", {
        "product": stripe_product["id"],
        "unit_amount": int(price_usd * 100),
        "currency": "usd",
        "metadata[product_id]": str(product_id),
    })

    # Store in DB
    with db.conn() as c:
        c.execute(
            """INSERT OR REPLACE INTO stripe_products
               (product_id, stripe_product_id, stripe_price_id, price_usd, active)
               VALUES (?,?,?,?,1)""",
            (product_id, stripe_product["id"], stripe_price["id"], price_usd)
        )

    log.info("Stripe product created: %s (price: $%.2f)", title, price_usd)
    return {"stripe_product_id": stripe_product["id"],
            "stripe_price_id": stripe_price["id"]}


def sync_all_products_to_stripe():
    """Ensure every published product in our DB has a Stripe product."""
    with db.conn() as c:
        products = c.execute(
            """SELECT p.id, p.title, p.type, p.price_usd, p.meta
               FROM products p
               LEFT JOIN stripe_products sp ON p.id = sp.product_id
               WHERE p.published_at IS NOT NULL
               AND sp.product_id IS NULL
               AND p.price_usd > 0"""
        ).fetchall()

    for row in products:
        meta = json.loads(row["meta"] or "{}")
        try:
            create_stripe_product(
                product_id=row["id"],
                title=row["title"],
                description=meta.get("back_cover_blurb", ""),
                price_usd=row["price_usd"] or 9.99,
                product_type=row["type"],
            )
        except Exception as e:
            log.error("Failed to create Stripe product for '%s': %s", row["title"], e)


# ─── CHECKOUT SESSION ─────────────────────────────────────────────────────────

def create_checkout_session(product_id: int, success_url: str,
                             cancel_url: str, customer_email: str = None) -> str:
    """Create a Stripe Checkout session and return the URL."""
    with db.conn() as c:
        sp = c.execute(
            "SELECT stripe_price_id FROM stripe_products WHERE product_id=? AND active=1",
            (product_id,)
        ).fetchone()

    if not sp:
        raise ValueError(f"No Stripe price found for product {product_id}")

    data = {
        "mode": "payment",
        "line_items[0][price]": sp["stripe_price_id"],
        "line_items[0][quantity]": "1",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata[product_id]": str(product_id),
        "payment_intent_data[metadata][product_id]": str(product_id),
        "allow_promotion_codes": "true",
        "billing_address_collection": "auto",
    }
    if customer_email:
        data["customer_email"] = customer_email

    session = _stripe("POST", "checkout/sessions", data)
    log.info("Checkout session created for product %d", product_id)
    return session["url"]


# ─── WEBHOOK HANDLER ──────────────────────────────────────────────────────────

def verify_webhook(payload: bytes, sig_header: str, secret: str) -> dict:
    """Verify Stripe webhook signature and return the event."""
    import hmac
    timestamp = None
    signatures = []

    for part in sig_header.split(","):
        k, v = part.split("=", 1)
        if k == "t":
            timestamp = int(v)
        elif k == "v1":
            signatures.append(v)

    if not timestamp or not signatures:
        raise ValueError("Invalid Stripe signature header")

    # Reject events older than 5 minutes
    if abs(time.time() - timestamp) > 300:
        raise ValueError("Webhook timestamp too old")

    signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
    expected = hmac.new(
        secret.encode(), signed_payload.encode(), hashlib.sha256
    ).hexdigest()

    if not any(hmac.compare_digest(expected, sig) for sig in signatures):
        raise ValueError("Webhook signature mismatch")

    return json.loads(payload)


def handle_webhook_event(event: dict) -> str:
    """Process a verified Stripe webhook event."""
    event_type = event["type"]
    log.info("Stripe webhook: %s", event_type)

    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        _on_payment_success(session)

    elif event_type == "payment_intent.payment_failed":
        pi = event["data"]["object"]
        log.warning("Payment failed: %s — %s", pi["id"],
                    pi.get("last_payment_error", {}).get("message"))

    elif event_type == "charge.refunded":
        charge = event["data"]["object"]
        _on_refund(charge)

    elif event_type == "payout.paid":
        payout = event["data"]["object"]
        log.info("Payout to bank: $%.2f %s", payout["amount"] / 100,
                 payout["currency"].upper())

    return "ok"


def _on_payment_success(session: dict):
    """Customer paid — record revenue and create download token."""
    product_id = session.get("metadata", {}).get("product_id")
    amount_usd = session.get("amount_total", 0) / 100.0
    customer_email = session.get("customer_details", {}).get("email", "")

    if product_id:
        db.record_revenue(int(product_id), "stripe", amount_usd)

    # Generate a secure, single-use download token
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.utcnow() + timedelta(hours=48)).isoformat()

    with db.conn() as c:
        c.execute(
            """INSERT INTO download_tokens
               (token, product_id, customer_email, expires_at, used)
               VALUES (?,?,?,?,0)""",
            (token, product_id, customer_email, expires_at)
        )

    log.info("Payment confirmed: $%.2f for product %s — token issued to %s",
             amount_usd, product_id, customer_email)
    return token


def _on_refund(charge: dict):
    """Handle a refund — deduct from revenue records."""
    refunded_usd = charge.get("amount_refunded", 0) / 100.0
    product_id = charge.get("metadata", {}).get("product_id")
    if product_id:
        db.record_revenue(int(product_id), "stripe_refund", -refunded_usd)
    log.info("Refund processed: -$%.2f", refunded_usd)


# ─── DOWNLOAD TOKEN VALIDATION ────────────────────────────────────────────────

def validate_download_token(token: str) -> dict | None:
    """Check if a download token is valid and not expired. Returns product info."""
    with db.conn() as c:
        row = c.execute(
            """SELECT dt.id, dt.product_id, dt.customer_email, dt.expires_at, dt.used,
                      p.title, p.type, p.file_path
               FROM download_tokens dt
               JOIN products p ON dt.product_id = p.id
               WHERE dt.token = ?""",
            (token,)
        ).fetchone()

    if not row:
        return None
    if row["used"]:
        return None
    if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
        return None

    return dict(row)


def mark_token_used(token: str):
    with db.conn() as c:
        c.execute("UPDATE download_tokens SET used=1 WHERE token=?", (token,))


# ─── REVENUE MONITORING ───────────────────────────────────────────────────────

def get_stripe_balance() -> dict:
    """Get current Stripe balance."""
    balance = _stripe("GET", "balance")
    available = sum(b["amount"] for b in balance.get("available", [])) / 100
    pending = sum(b["amount"] for b in balance.get("pending", [])) / 100
    log.info("Stripe balance — Available: $%.2f | Pending: $%.2f", available, pending)
    return {"available_usd": available, "pending_usd": pending}


def get_recent_transactions(limit: int = 20) -> list[dict]:
    """Fetch recent Stripe charges."""
    data = _stripe("GET", "charges", params={"limit": limit})
    charges = data.get("data", [])
    return [
        {
            "id": c["id"],
            "amount_usd": c["amount"] / 100,
            "status": c["status"],
            "email": c.get("billing_details", {}).get("email", ""),
            "description": c.get("description", ""),
            "created": datetime.fromtimestamp(c["created"]).isoformat(),
            "product_id": c.get("metadata", {}).get("product_id"),
        }
        for c in charges
    ]


def transaction_monitor_report() -> dict:
    """Full autonomous transaction health report."""
    balance = get_stripe_balance()
    transactions = get_recent_transactions(50)
    revenue = db.revenue_summary()

    successful = [t for t in transactions if t["status"] == "succeeded"]
    failed = [t for t in transactions if t["status"] == "failed"]
    total_recent = sum(t["amount_usd"] for t in successful)

    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "stripe_balance": balance,
        "recent_50_transactions": {
            "successful": len(successful),
            "failed": len(failed),
            "volume_usd": total_recent,
        },
        "all_time_revenue": revenue,
    }
    log.info("Transaction report: $%.2f balance | $%.2f recent volume",
             balance["available_usd"], total_recent)
    return report
