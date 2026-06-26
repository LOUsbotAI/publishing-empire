#!/usr/bin/env bash
# Quick health check for all system components.
set -euo pipefail

ok() { echo "✅ $*"; }
fail() { echo "❌ $*"; }
warn() { echo "⚠️  $*"; }

echo "=== Publishing Empire Health Check ==="
echo ""

# 1. Webhook
if curl -sf http://127.0.0.1:8001/health >/dev/null 2>&1; then
    ok "Stripe webhook running on :8001"
else
    fail "Stripe webhook NOT reachable at :8001 — run: pm2 start pm2.config.js"
fi

# 2. PM2
if command -v pm2 &>/dev/null; then
    ONLINE=$(pm2 jlist 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(1 for p in d if p['pm2_env']['status']=='online'))" 2>/dev/null || echo 0)
    ok "PM2 available — $ONLINE process(es) online"
else
    warn "PM2 not installed — install with: npm i -g pm2"
fi

# 3. Exports folder
EXPORTS="$HOME/lousta-core/output/exports"
if [ -d "$EXPORTS" ]; then
    COUNT=$(find "$EXPORTS" -maxdepth 2 -type f | wc -l)
    ok "Exports folder exists — $COUNT file(s)"
else
    warn "Exports folder missing: $EXPORTS (created on first run)"
fi

# 4. Revenue log
REVENUE="$HOME/.lousta_system_core/vault/revenue_log.jsonl"
if [ -f "$REVENUE" ]; then
    LINES=$(wc -l < "$REVENUE")
    ok "Revenue log — $LINES event(s) logged"
else
    warn "Revenue log empty (no live webhook events yet)"
fi

# 5. Key audit
python3 "$(dirname "$0")/key_audit.py" 2>/dev/null \
    | python3 -c "
import sys, json
d = json.load(sys.stdin)
missing = [k['key'] for k in d['keys'] if k['status'] == 'MISSING']
found   = [k['key'] for k in d['keys'] if k['status'] != 'MISSING']
if found:   print(f'✅ Keys present: {len(found)}')
if missing: print(f'⚠️  Keys missing: {\" \".join(missing)}')
" 2>/dev/null || warn "Key audit skipped — run scripts/key_audit.py manually"

echo ""
echo "=== Done ==="
