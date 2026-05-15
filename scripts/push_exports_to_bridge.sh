#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# LOUSTA — Push Finished Exports to Publishing Empire Bridge
# ============================================================
# Run this in Termux after book generation to auto-list on store.
#
# Usage:
#   bash push_exports_to_bridge.sh                     # push all new
#   bash push_exports_to_bridge.sh ~/lousta-core/output/exports/my-book/
#
# Requires: BRIDGE_URL and BRIDGE_API_KEY in ~/.lousta_system_core/secrets/.env

set -euo pipefail

ENV_FILE="$HOME/.lousta_system_core/secrets/.env"
[ -f "$ENV_FILE" ] && source "$ENV_FILE"

BRIDGE_URL="${BRIDGE_URL:-http://localhost:8001}"
BRIDGE_KEY="${BRIDGE_API_KEY:-change_this_bridge_key}"
EXPORTS_DIR="${1:-$HOME/lousta-core/output/exports}"
PUSHED_LOG="$HOME/.lousta_system_core/vault/pushed_exports.txt"
touch "$PUSHED_LOG"

echo "================================================"
echo "  LOUSTA — Export Push to Publishing Bridge"
echo "  Bridge: $BRIDGE_URL"
echo "  Exports: $EXPORTS_DIR"
echo "================================================"
echo ""

# Health check
HEALTH=$(curl -sf "$BRIDGE_URL/bridge/health" -H "X-Bridge-Key: $BRIDGE_KEY" 2>/dev/null || echo "FAIL")
if echo "$HEALTH" | grep -q '"ok"'; then
    echo "✅ Bridge is healthy"
else
    echo "❌ Bridge not reachable at $BRIDGE_URL"
    echo "   Start bridge: python3 termux_bridge.py"
    exit 1
fi
echo ""

PUSHED=0
SKIPPED=0
ERRORS=0

for EXPORT_DIR in "$EXPORTS_DIR"/*/; do
    [ -d "$EXPORT_DIR" ] || continue
    EXPORT_JSON="$EXPORT_DIR/export.json"
    [ -f "$EXPORT_JSON" ] || continue

    SLUG=$(basename "$EXPORT_DIR")

    # Skip already pushed
    if grep -qF "$SLUG" "$PUSHED_LOG" 2>/dev/null; then
        echo "  ⏭  Already pushed: $SLUG"
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    echo "  📤 Pushing: $SLUG"
    RESPONSE=$(curl -sf \
        -X POST "$BRIDGE_URL/bridge/export" \
        -H "Content-Type: application/json" \
        -H "X-Bridge-Key: $BRIDGE_KEY" \
        -d @"$EXPORT_JSON" 2>/dev/null || echo '{"status":"error"}')

    STATUS=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "error")

    case "$STATUS" in
        registered)
            PRODUCT_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('product_id','?'))" 2>/dev/null || echo "?")
            echo "     ✅ Registered as product #$PRODUCT_ID"
            echo "$SLUG" >> "$PUSHED_LOG"
            PUSHED=$((PUSHED + 1))
            ;;
        already_exists)
            echo "     ℹ️  Already in store"
            echo "$SLUG" >> "$PUSHED_LOG"
            SKIPPED=$((SKIPPED + 1))
            ;;
        *)
            echo "     ❌ Error: $RESPONSE"
            ERRORS=$((ERRORS + 1))
            ;;
    esac
done

echo ""
echo "================================================"
echo "  DONE: $PUSHED pushed | $SKIPPED skipped | $ERRORS errors"
echo "================================================"
echo ""

# Show current catalogue
echo "📚 Current store catalogue:"
curl -sf "$BRIDGE_URL/bridge/catalogue" \
    -H "X-Bridge-Key: $BRIDGE_KEY" 2>/dev/null | \
    python3 -c "
import sys, json
data = json.load(sys.stdin)
products = data.get('products', [])
print(f'  {len(products)} products live')
for p in products[:5]:
    print(f'  - {p[\"title\"]} (\${p[\"price_usd\"]:.2f}) [{p[\"type\"]}]')
if len(products) > 5:
    print(f'  ... and {len(products)-5} more')
" 2>/dev/null || echo "  (could not fetch catalogue)"
