#!/bin/bash
# Publishing Empire — Start Everything
set -e

cd "$(dirname "$0")"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Publishing Empire — Booting"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Load env
[ -f .env ] && export $(grep -v '^#' .env | xargs)

# Initialize database
python3 -c "import database; database.init_db(); print('✅ Database ready')"

# Start web storefront (background)
echo "🌐 Starting storefront on port ${PORT:-8000}..."
python3 website/app.py &
WEB_PID=$!
echo "   PID: $WEB_PID"

# Start Cloudflare Tunnel (exposes store to internet)
if [ -n "$CF_TUNNEL_TOKEN" ]; then
  echo "☁️  Starting Cloudflare Tunnel..."
  cloudflared tunnel run --token "$CF_TUNNEL_TOKEN" &
  CF_PID=$!
  echo "   PID: $CF_PID"
else
  echo "⚠️  CF_TUNNEL_TOKEN not set — store only accessible locally"
fi

# Start Termux bridge (connects to existing Node.js system on port 8001)
echo "🔗 Starting Termux bridge on port 8001..."
python3 termux_bridge.py &
BRIDGE_PID=$!
echo "   PID: $BRIDGE_PID"

# Start content orchestrator (background)
echo "🤖 Starting content orchestrator..."
python3 orchestrator.py &
ORC_PID=$!
echo "   PID: $ORC_PID"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ Empire is LIVE"
echo "  Store:        http://localhost:${PORT:-8000}"
echo "  Admin report: http://localhost:${PORT:-8000}/admin/report?key=\$ADMIN_KEY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Press Ctrl+C to stop all processes"

trap "echo ''; echo 'Stopping...'; kill $WEB_PID $ORC_PID $BRIDGE_PID ${CF_PID:-} 2>/dev/null; exit 0" SIGINT SIGTERM
wait
