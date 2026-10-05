#!/data/data/com.termux/files/usr/bin/bash
# Stage the 11082 hub into supervised_dev. Copies files only. Starts nothing.
export PATH="/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/bin/applets"
printf '\033[36m=== PASTE START: HUB 11082 STAGE ===\033[0m\n'
echo "MUTATION=YES (isolated supervised_dev candidate only)"
echo "LIVE_1182_MUTATION=NO"; echo "SERVICE_START=NO"; echo "EXECUTION=NO"; echo "PRODUCTION=LOCKED"
SRC="$(cd "$(dirname "$0")" && pwd)"
ROOT="$HOME/bluebits/empire_director_v1"
DEST="$ROOT/supervised_dev/hub_11082_v1/CANDIDATE_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$DEST" || { echo "HOLD=CANNOT_CREATE_DEST"; exit 1; }
cp "$SRC/hub_11082.py" "$SRC/index.html" "$SRC/modules.json" "$SRC/START_11082.sh" "$DEST/" || { echo "HOLD=COPY_FAILED"; exit 1; }
chmod +x "$DEST/START_11082.sh"
python3 -c "import ast,sys;ast.parse(open(sys.argv[1]).read())" "$DEST/hub_11082.py" && echo "AST=PASS" || { echo "HOLD=AST_FAIL"; exit 1; }
python3 -c "import json,sys;json.load(open(sys.argv[1]))" "$DEST/modules.json" && echo "MODULES_JSON=PASS" || { echo "HOLD=JSON_FAIL"; exit 1; }
if grep -nE 'subprocess|os\.system|Popen|11884|tmux/send|run-approved|/loukey/auto' "$DEST/hub_11082.py" "$DEST/index.html" | grep -v '^[^:]*:[0-9]*:  - no proxying'; then
  echo "HOLD=EXECUTION_PATH_FOUND"; exit 1
fi
echo "NO_EXECUTION_PATH=PASS"
( cd "$DEST" && sha256sum hub_11082.py index.html modules.json START_11082.sh > SHA256SUMS.txt && cat SHA256SUMS.txt )
C=$(curl -s -o /dev/null --max-time 2 -w '%{http_code}' http://127.0.0.1:11082/ 2>/dev/null || true)
[ "${C:-000}" = "000" ] && echo "PORT_11082=FREE" || echo "PORT_11082=IN_USE_HTTP_$C (check what owns it before starting)"
printf '\033[32mPASS=HUB_11082_STAGED\033[0m\n'
echo "CANDIDATE_ROOT=$DEST"
echo "NEXT=bash \"$DEST/START_11082.sh\"   then open http://127.0.0.1:11082/"
printf '\033[36m=== PASTE END: HUB 11082 STAGE ===\033[0m\n'
