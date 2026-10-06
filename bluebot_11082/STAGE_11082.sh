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
cp "$SRC/hub_11082.py" "$SRC/brains.py" "$SRC/voice.py" "$SRC/keys.env.example" "$SRC/index.html" "$SRC/modules.json" "$SRC/work_orders.json" "$SRC/START_11082.sh" "$SRC/PROMOTE_MODULE.sh" "$SRC/BUILD_CHARTER.md" "$DEST/" || { echo "HOLD=COPY_FAILED"; exit 1; }
mkdir -p "$DEST/modules" "$DEST/tools" && cp "$SRC/modules/"*.js "$DEST/modules/" && cp "$SRC/tools/check_module.py" "$DEST/tools/" || { echo "HOLD=COPY_FAILED"; exit 1; }
mkdir -p "$ROOT/supervised_dev/hub_modules"
chmod +x "$DEST/START_11082.sh" "$DEST/PROMOTE_MODULE.sh"
for M in "$DEST/modules/"*.js; do python3 "$DEST/tools/check_module.py" "$M" >/dev/null && echo "MODULE_CHECK=PASS $(basename "$M")" || { echo "HOLD=MODULE_CHECK_FAILED $M"; exit 1; }; done
python3 -c "import ast,sys;ast.parse(open(sys.argv[1]).read())" "$DEST/hub_11082.py" && echo "AST=PASS" || { echo "HOLD=AST_FAIL"; exit 1; }
python3 -c "import json,sys;[json.load(open(a)) for a in sys.argv[1:]]" "$DEST/modules.json" "$DEST/work_orders.json" && echo "JSON=PASS" || { echo "HOLD=JSON_FAIL"; exit 1; }
# real execution primitives in the server (docstring excluded), and any browser write other than /hub/chat
if python3 - "$DEST/hub_11082.py" <<'PY'
import ast, sys
t = ast.parse(open(sys.argv[1]).read())
bad = [n.names[0].name if isinstance(n, ast.Import) else n.module for n in ast.walk(t)
       if isinstance(n, (ast.Import, ast.ImportFrom)) and (n.names[0].name if isinstance(n, ast.Import) else n.module) in ("subprocess", "pty", "socket", "shutil", "ctypes")]
calls = [n.func.attr for n in ast.walk(t) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("system", "popen", "execv", "execvp", "spawnv", "remove", "unlink", "rmtree")]
print("SERVER_EXEC_SCAN=" + ("HOLD " + ",".join(bad + calls) if bad or calls else "CLEAN"))
sys.exit(1 if bad or calls else 0)
PY
then :; else echo "HOLD=EXECUTION_PATH_FOUND"; exit 1; fi
W=$(grep -oE "method:'(POST|PUT|PATCH|DELETE)'" "$DEST/index.html" | grep -c . )
C=$(grep -oE "fetch\('/hub/(chat|transcribe)',\{method:'POST'" "$DEST/index.html" | grep -c . )
if [ "$W" != "$C" ] || [ "$C" != "2" ]; then echo "HOLD=UNEXPECTED_BROWSER_WRITE ($W writes, $C allowed)"; exit 1; fi
echo "NO_EXECUTION_PATH=PASS"
( cd "$DEST" && sha256sum hub_11082.py brains.py voice.py index.html modules.json work_orders.json START_11082.sh PROMOTE_MODULE.sh tools/check_module.py modules/*.js > SHA256SUMS.txt && cat SHA256SUMS.txt )
C=$(curl -s -o /dev/null --max-time 2 -w '%{http_code}' http://127.0.0.1:11082/ 2>/dev/null || true)
[ "${C:-000}" = "000" ] && echo "PORT_11082=FREE" || echo "PORT_11082=IN_USE_HTTP_$C (check what owns it before starting)"
if [ -f "$HOME/.lousta/keys.env" ]; then chmod 600 "$HOME/.lousta/keys.env"; echo "KEYS_FILE=present (private)"; else echo "KEYS_FILE=none (optional: mkdir -p ~/.lousta && cp \"$DEST/keys.env.example\" ~/.lousta/keys.env && chmod 600 ~/.lousta/keys.env)"; fi
printf '\033[32mPASS=HUB_11082_STAGED\033[0m\n'
echo "CANDIDATE_ROOT=$DEST"
echo "NEXT=bash \"$DEST/START_11082.sh\"   then open http://127.0.0.1:11082/"
printf '\033[36m=== PASTE END: HUB 11082 STAGE ===\033[0m\n'
