#!/bin/bash
# =============================================================
# LOUSTA KEY ROTATION WIZARD
# Run this in Termux any time you get a fresh API key.
# Backs up your current .env before making any changes.
#
# Usage: bash ~/publishing-empire/scripts/update_keys.sh
# =============================================================

set -e

ENV_FILE="$HOME/.lousta_system_core/secrets/.env"
VAULT_DIR="$HOME/.lousta_system_core/vault"
BACKUP="$VAULT_DIR/.env.backup.$(date +%Y%m%d_%H%M%S)"

mkdir -p "$(dirname "$ENV_FILE")" "$VAULT_DIR"

# Back up current .env
if [ -f "$ENV_FILE" ]; then
    cp "$ENV_FILE" "$BACKUP"
    echo "Backed up current .env → $BACKUP"
fi

touch "$ENV_FILE"
chmod 600 "$ENV_FILE"

# ─── Helper ──────────────────────────────────────────────────
set_key() {
    local KEY="$1"
    local LABEL="$2"
    local HINT="$3"

    echo ""
    echo "── $KEY ──────────────────────────────────────────────"
    echo "   $LABEL"
    [ -n "$HINT" ] && echo "   Format: $HINT"
    printf "   New value (Enter to skip): "
    read -r NEW_VAL

    if [ -z "$NEW_VAL" ]; then
        echo "   Skipped."
        return
    fi

    # Remove any existing entry for this key, then append fresh value
    grep -v "^${KEY}=" "$ENV_FILE" > "${ENV_FILE}.tmp" 2>/dev/null || true
    mv "${ENV_FILE}.tmp" "$ENV_FILE"
    printf '%s=%s\n' "$KEY" "$NEW_VAL" >> "$ENV_FILE"
    echo "   ✅ Saved."
}

echo ""
echo "============================================================"
echo "  LOUSTA KEY ROTATION WIZARD"
echo "  Saving to: $ENV_FILE"
echo "  Press Enter to skip any key you don't have yet."
echo "============================================================"

# ─── Critical: AI generation ──────────────────────────────────
set_key "ANTHROPIC_API_KEY" \
    "Claude AI — book content generation (CRITICAL)" \
    "sk-ant-api03-..."

set_key "GEMINI_API_KEY" \
    "Google Gemini — aistudio.google.com/apikey" \
    "AIzaSy..."

set_key "GROK_API_KEY" \
    "Grok/xAI — console.x.ai" \
    "xai-..."

# ─── Audio ────────────────────────────────────────────────────
set_key "ELEVENLABS_API_KEY" \
    "ElevenLabs TTS — elevenlabs.io → API Keys" \
    "xi-..."

# ─── Payments ─────────────────────────────────────────────────
set_key "STRIPE_SECRET_KEY" \
    "Stripe live — dashboard.stripe.com → Developers → API keys → Roll" \
    "sk_live_..."

set_key "STRIPE_WEBHOOK_SECRET" \
    "Stripe webhook signing secret" \
    "whsec_..."

set_key "LEMONSQUEEZY_API_KEY" \
    "LemonSqueezy — app.lemonsqueezy.com → Settings → API" \
    "..."

# ─── Infrastructure ───────────────────────────────────────────
set_key "CF_TUNNEL_TOKEN" \
    "Cloudflare Tunnel — dash.cloudflare.com → Zero Trust → Tunnels" \
    "eyJh..."

set_key "TELEGRAM_BOT_TOKEN" \
    "Telegram bot — @BotFather → /newbot → copy token" \
    "123456:AAF..."

set_key "TELEGRAM_CHAT_ID" \
    "Your Telegram chat ID — message the bot, check /getUpdates" \
    "123456789"

echo ""
echo "============================================================"
echo "  ✅ Keys saved to: $ENV_FILE"
echo ""
echo "  Next steps:"
echo "    1. Run preflight to verify:"
echo "       node ~/publishing-empire/scripts/termux_preflight.js"
echo ""
echo "    2. If preflight passes, restart everything:"
echo "       pm2 restart all"
echo "============================================================"
