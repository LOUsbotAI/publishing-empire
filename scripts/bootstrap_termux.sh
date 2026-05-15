#!/bin/bash
# =============================================================
# LOUSTA EMPIRE — TERMUX BOOTSTRAP
# Single command to bring the entire system online safely.
#
# What this does:
#   1. Validates all API keys (pre-flight)
#   2. If keys fail → runs key rotation wizard
#   3. Starts the Cloudflare tunnel
#   4. Restarts all PM2 processes
#   5. Confirms everything is live
#
# Usage:
#   bash ~/publishing-empire/scripts/bootstrap_termux.sh
# =============================================================

set -e

EMPIRE_DIR="$HOME/publishing-empire"
ENV_FILE="$HOME/.lousta_system_core/secrets/.env"
PREFLIGHT="$EMPIRE_DIR/scripts/termux_preflight.js"
UPDATER="$EMPIRE_DIR/scripts/update_keys.sh"

# Load .env
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
fi

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║         LOUSTA EMPIRE — BOOTSTRAP SEQUENCE          ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ─── Step 1: Pre-flight API check ─────────────────────────────
echo "── Step 1/4: API Pre-flight ─────────────────────────────"
if node "$PREFLIGHT"; then
    echo "   Pre-flight passed."
else
    echo ""
    echo "   ⚠️  API keys need updating. Launching key wizard..."
    echo ""
    bash "$UPDATER"

    echo ""
    echo "   Re-running pre-flight after key update..."
    if ! node "$PREFLIGHT"; then
        echo ""
        echo "   ❌ Pre-flight still failing. Fix keys manually:"
        echo "      bash $UPDATER"
        echo "   Then re-run bootstrap."
        exit 1
    fi
fi

# ─── Step 2: Cloudflare tunnel ────────────────────────────────
echo ""
echo "── Step 2/4: Cloudflare Tunnel ──────────────────────────"
if pm2 describe CF-Tunnel > /dev/null 2>&1; then
    pm2 restart CF-Tunnel
    echo "   CF-Tunnel restarted."
elif [ -n "$CF_TUNNEL_TOKEN" ]; then
    pm2 start "cloudflared tunnel run --token $CF_TUNNEL_TOKEN" \
        --name "CF-Tunnel" \
        --restart-delay 5000 \
        --max-restarts 10
    echo "   CF-Tunnel started."
else
    echo "   ⚠️  CF_TUNNEL_TOKEN not set — tunnel skipped."
fi

# ─── Step 3: Restart PM2 processes ────────────────────────────
echo ""
echo "── Step 3/4: PM2 Process Restart ────────────────────────"
pm2 restart all 2>/dev/null || echo "   No existing PM2 processes to restart."
sleep 3

# ─── Step 4: Status report ────────────────────────────────────
echo ""
echo "── Step 4/4: Live Status ────────────────────────────────"
pm2 list

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║               EMPIRE IS LIVE                        ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Dashboard:    http://localhost:8000"
echo "  Store bridge: http://localhost:8001"
echo "  Stripe gate:  http://localhost:3011"
echo ""
echo "  Watch logs:   pm2 logs --lines 50"
echo "  Full status:  pm2 monit"
echo ""
