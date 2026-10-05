#!/data/data/com.termux/files/usr/bin/bash
# OWNER ACTION. Promote one team-built module into the running hub.
# Usage: bash PROMOTE_MODULE.sh /path/to/<name>.js [tile_id] [category]
# Checks it, backs up any old copy, installs it, and points a tile at it. No restart needed.
export PATH="/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/bin/applets"
printf '\033[36m=== PASTE START: PROMOTE HUB MODULE ===\033[0m\n'
echo "AUTHORITY=OWNER"; echo "EXECUTION=NO"; echo "SERVICE_RESTART=NO"; echo "PRODUCTION=LOCKED"
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$1"; NAME="$(basename "${SRC:-x}" .js)"; TILE="${2:-$NAME}"; CAT="${3:-Observe}"
[ -f "$SRC" ] || { echo "HOLD=NO_SUCH_FILE $SRC"; exit 1; }
python3 "$HERE/tools/check_module.py" "$SRC" || { echo "HOLD=CHECK_FAILED (nothing installed)"; exit 1; }
mkdir -p "$HERE/modules" "$HERE/modules/.backup"
STAMP="$(date +%Y%m%d_%H%M%S)"
[ -f "$HERE/modules/$NAME.js" ] && cp "$HERE/modules/$NAME.js" "$HERE/modules/.backup/$NAME.$STAMP.js" && echo "BACKUP=modules/.backup/$NAME.$STAMP.js"
[ -f "$HERE/modules.local.json" ] && cp "$HERE/modules.local.json" "$HERE/modules/.backup/modules.local.$STAMP.json"
cp "$SRC" "$HERE/modules/$NAME.js"
python3 - "$HERE" "$TILE" "$NAME" "$CAT" <<'PY'
import json, os, sys
hub, tile, name, cat = sys.argv[1:]
sys.path.insert(0, hub)
import hub_11082
hub_11082.HERE = hub
merged = hub_11082.load_config()
lp = os.path.join(hub, "modules.local.json")
try:
    local = json.load(open(lp))
except Exception:
    local = {}
if any(m.get("id") == tile for m in merged.get("modules", [])):
    local.setdefault("modules_patch", {}).setdefault(tile, {})["native"] = name
else:
    local.setdefault("modules_add", []).insert(0, {"id": tile, "label": name.replace("_", " ").title(), "icon": "◆", "category": cat, "native": name})
json.dump(local, open(lp, "w"), indent=1, ensure_ascii=False)
print("TILE=%s NATIVE=%s.js (modules.local.json)" % (tile, name))
PY
sha256sum "$HERE/modules/$NAME.js"
echo "$STAMP PROMOTED $NAME.js -> tile $TILE $(sha256sum "$HERE/modules/$NAME.js" | cut -c1-16)" >> "$HERE/modules/PROMOTIONS.log"
printf '\033[32mPASS=MODULE_PROMOTED\033[0m  (reload the hub page)\n'
echo "ROLLBACK=rm \"$HERE/modules/$NAME.js\" and restore modules/.backup/modules.local.$STAMP.json (if any) to modules.local.json"
printf '\033[36m=== PASTE END: PROMOTE HUB MODULE ===\033[0m\n'
