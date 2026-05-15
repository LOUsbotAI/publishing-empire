"""
LemonSqueezy Agent
==================
LemonSqueezy is a Merchant of Record:
  - Handles all global VAT/GST/sales tax automatically
  - Pays YOU directly to your bank weekly
  - No Stripe, no middleman, no payout failures
  - Simple REST API

Setup:
  1. Sign up at app.lemonsqueezy.com
  2. Settings → API → Generate API key → LEMONSQUEEZY_API_KEY in .env
  3. Settings → Stores → create your store → LEMONSQUEEZY_STORE_ID in .env
  4. Payments → Payouts → link your bank account (BSB + account number for AU)
"""
import json
import logging
import os

import requests
import database as db

log = logging.getLogger("lemonsqueezy")

BASE = "https://api.lemonsqueezy.com/v1"


def _headers():
    key = os.getenv("LEMONSQUEEZY_API_KEY", "")
    if not key:
        raise RuntimeError("LEMONSQUEEZY_API_KEY not set")
    return {
        "Authorization": f"Bearer {key}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
    }


def _store_id():
    sid = os.getenv("LEMONSQUEEZY_STORE_ID", "")
    if not sid:
        raise RuntimeError("LEMONSQUEEZY_STORE_ID not set")
    return sid


# ─── PRODUCT MANAGEMENT ───────────────────────────────────────────────────────

def create_product(title: str, description: str, price_usd: float,
                   product_type: str = "ebook") -> dict:
    """Create a LemonSqueezy product + variant (price)."""
    # Create product
    product_resp = requests.post(f"{BASE}/products", headers=_headers(), json={
        "data": {
            "type": "products",
            "attributes": {
                "name": title[:100],
                "description": description[:500] if description else "",
                "status": "published",
            },
            "relationships": {
                "store": {"data": {"type": "stores", "id": _store_id()}}
            }
        }
    }, timeout=30)
    product_resp.raise_for_status()
    product_id = product_resp.json()["data"]["id"]

    # Create variant (the actual purchasable item with price)
    variant_resp = requests.post(f"{BASE}/variants", headers=_headers(), json={
        "data": {
            "type": "variants",
            "attributes": {
                "name": "Standard",
                "price": int(price_usd * 100),
                "is_subscription": False,
                "has_free_trial": False,
                "status": "published",
            },
            "relationships": {
                "product": {"data": {"type": "products", "id": product_id}}
            }
        }
    }, timeout=30)
    variant_resp.raise_for_status()
    variant_id = variant_resp.json()["data"]["id"]

    log.info("LemonSqueezy product created: %s (product: %s, variant: %s)",
             title, product_id, variant_id)
    return {"product_id": product_id, "variant_id": variant_id}


def get_checkout_url(variant_id: str, custom_data: dict = None) -> str:
    """Create a LemonSqueezy checkout URL for a product variant."""
    payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "checkout_options": {
                    "button_color": "#d4a853",
                },
                "checkout_data": {
                    "custom": custom_data or {},
                },
                "expires_at": None,
            },
            "relationships": {
                "store": {"data": {"type": "stores", "id": _store_id()}},
                "variant": {"data": {"type": "variants", "id": variant_id}},
            }
        }
    }
    resp = requests.post(f"{BASE}/checkouts", headers=_headers(),
                         json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()["data"]["attributes"]["url"]


def sync_product_to_ls(product_id: int, title: str, description: str,
                        price_usd: float, product_type: str) -> dict:
    """Create a LemonSqueezy product for a published item and store the IDs."""
    with db.conn() as c:
        existing = c.execute(
            "SELECT ls_product_id, ls_variant_id FROM ls_products WHERE product_id=?",
            (product_id,)
        ).fetchone()
    if existing:
        return dict(existing)

    ids = create_product(title, description, price_usd, product_type)
    with db.conn() as c:
        c.execute(
            """INSERT INTO ls_products (product_id, ls_product_id, ls_variant_id, price_usd)
               VALUES (?,?,?,?)""",
            (product_id, ids["product_id"], ids["variant_id"], price_usd)
        )
    return ids


def sync_all_products():
    """Push all published products to LemonSqueezy if not already there."""
    with db.conn() as c:
        products = c.execute(
            """SELECT p.id, p.title, p.type, p.price_usd, p.meta
               FROM products p
               LEFT JOIN ls_products ls ON p.id = ls.product_id
               WHERE p.published_at IS NOT NULL AND p.price_usd > 0
               AND ls.product_id IS NULL"""
        ).fetchall()

    import json as _json
    for row in products:
        meta = _json.loads(row["meta"] or "{}")
        try:
            sync_product_to_ls(
                product_id=row["id"],
                title=row["title"],
                description=meta.get("back_cover_blurb", ""),
                price_usd=row["price_usd"] or 9.99,
                product_type=row["type"],
            )
        except Exception as e:
            log.error("Failed to sync product %d to LemonSqueezy: %s", row["id"], e)


# ─── WEBHOOK HANDLER ──────────────────────────────────────────────────────────

def handle_webhook(payload: dict) -> str:
    """Process LemonSqueezy webhook events."""
    event = payload.get("meta", {}).get("event_name", "")
    log.info("LemonSqueezy webhook: %s", event)

    if event == "order_created":
        order = payload.get("data", {}).get("attributes", {})
        if order.get("status") == "paid":
            _on_order_paid(payload["data"])

    return "ok"


def _on_order_paid(order_data: dict):
    import secrets
    from datetime import datetime, timedelta

    attrs = order_data.get("attributes", {})
    amount_usd = attrs.get("total", 0) / 100.0
    email = attrs.get("user_email", "")
    product_id = attrs.get("custom_data", {}).get("product_id")
    order_id = order_data.get("id")

    if product_id:
        db.record_revenue(int(product_id), "lemonsqueezy", amount_usd)

    token = secrets.token_urlsafe(32)
    expires = (datetime.utcnow() + timedelta(hours=48)).isoformat()

    with db.conn() as c:
        c.execute(
            """INSERT OR IGNORE INTO download_tokens
               (token, product_id, customer_email, expires_at, used)
               VALUES (?,?,?,?,0)""",
            (token, int(product_id) if product_id else None, email, expires)
        )
        c.execute(
            """INSERT OR IGNORE INTO orders
               (stripe_session_id, product_id, customer_email,
                amount_usd, status, download_token)
               VALUES (?,?,?,?,'paid',?)""",
            (f"ls_{order_id}", int(product_id) if product_id else None,
             email, amount_usd, token)
        )

    log.info("LemonSqueezy order paid: $%.2f from %s — download token issued", amount_usd, email)
