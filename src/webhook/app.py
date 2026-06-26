"""
Stripe checkout webhook receiver.
Logs real payment events to the revenue JSONL vault.
Runs on port 8001 (matches data_map.csv health check).
"""
import os
import json
import hmac
import hashlib
import pathlib
import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv(pathlib.Path.home() / ".lousta_system_core" / "secrets" / ".env")

STRIPE_SECRET = os.getenv("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
REVENUE_LOG = pathlib.Path.home() / ".lousta_system_core" / "vault" / "revenue_log.jsonl"
REVENUE_LOG.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)

REAL_EVENTS = {
    "checkout.session.completed",
    "charge.succeeded",
    "payment_intent.succeeded",
}


def _verify_signature(payload: bytes, sig_header: str) -> bool:
    if not WEBHOOK_SECRET:
        return False
    try:
        parts = {p.split("=")[0]: p.split("=")[1] for p in sig_header.split(",")}
        ts = parts["t"]
        v1 = parts["v1"]
        signed = f"{ts}.{payload.decode()}"
        expected = hmac.new(
            WEBHOOK_SECRET.encode(), signed.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, v1)
    except Exception:
        return False


def _is_test_event(event: dict) -> bool:
    obj = event.get("data", {}).get("object", {})
    # Stripe test-mode IDs start with specific prefixes
    payment_id = obj.get("payment_intent", "") or obj.get("id", "")
    return str(payment_id).startswith("pi_test") or event.get("livemode") is False


def _log_event(event: dict, verified: bool) -> None:
    record = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "event_id": event.get("id"),
        "type": event.get("type"),
        "livemode": event.get("livemode"),
        "verified_sig": verified,
        "amount": (
            event.get("data", {})
            .get("object", {})
            .get("amount_total")
            or event.get("data", {}).get("object", {}).get("amount")
        ),
        "currency": (
            event.get("data", {}).get("object", {}).get("currency")
        ),
    }
    with open(REVENUE_LOG, "a") as f:
        f.write(json.dumps(record) + "\n")


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "stripe-webhook", "port": 8001}), 200


@app.post("/webhook")
def webhook():
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature", "")
    verified = _verify_signature(payload, sig)

    try:
        event = json.loads(payload)
    except ValueError:
        return jsonify({"error": "invalid JSON"}), 400

    if event.get("type") not in REAL_EVENTS:
        return jsonify({"status": "ignored", "type": event.get("type")}), 200

    if _is_test_event(event):
        return jsonify({"status": "skipped", "reason": "test_event"}), 200

    _log_event(event, verified)
    return jsonify({"status": "logged", "event_id": event.get("id")}), 200


if __name__ == "__main__":
    port = int(os.getenv("WEBHOOK_PORT", 8001))
    app.run(host="0.0.0.0", port=port)
