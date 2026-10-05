#!/data/data/com.termux/files/usr/bin/bash
# LOUSTA CENSUS: READ-ONLY. Collects what is needed to bring the system up and to direct BlueBot.
# Writes one report file (secrets masked). Starts, stops, edits and POSTs nothing. Never touches 11884.
export PATH="/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/bin/applets"
ROOT="$HOME/bluebits/empire_director_v1"
WB="$ROOT/supervised_dev/1182_bluebot_chat_installation_ready_v1/BLUEBOT_CHAT_INSTALLATION_READY_V1_20260926T020840Z/workbench"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="$HOME/LOUSTA_CENSUS_$STAMP.txt"
MASK='s/((api[_-]?key|token|secret|password|bearer|authorization|xai|sk-)[A-Za-z0-9_-]*["'"'"']?[=: ]+["'"'"']?)[^ "'"'"',}]+/\1***MASKED***/Ig'
MASK2='s/(Bearer[[:space:]]+)[^ "'"'"',}]+/\1***MASKED***/Ig; s/\b(sk-|xai-|gsk_|ghp_|github_pat_|AIza|sk_live_|sk_test_|rk_live_|whsec_|hf_)[A-Za-z0-9_-]{6,}/\1***MASKED***/g'
sec(){ printf '\n==================== %s ====================\n' "$1"; }

{
echo "LOUSTA CENSUS $STAMP"
echo "MUTATION=NO  EXECUTION=NO  RESTART=NO  POST=NO  11884=NOT_TOUCHED  PRODUCTION=LOCKED"
echo "ANDROID=$(getprop ro.build.version.release 2>/dev/null) SDK=$(getprop ro.build.version.sdk 2>/dev/null) DEVICE=$(getprop ro.product.model 2>/dev/null)"
df -h "$HOME" 2>/dev/null | tail -1

sec "A. LIVE PORTS (GET only)"
for X in "1182 /api/status" "11880 /api/status" "11882 /" "11770 /loukey/status" "11883 /" \
         "18082 /" "18097 /" "1185 /" "11902 /" "6205 /health" "11437 /v1/models" "11438 /v1/models" "11082 /hub/status"; do
  set -- $X
  C=$(curl -s -o /dev/null --connect-timeout 1 --max-time 3 -w '%{http_code}' "http://127.0.0.1:$1$2" 2>/dev/null)
  printf '%-6s %-16s HTTP_%s\n' "$1" "$2" "${C:-000}"
done
echo "11884 NOT_PROBED (owner-manual only)"

sec "B. TMUX + PROCESSES"
tmux -L lousta-bluebot-studio list-windows -F '#{window_index}|#{window_name}|#{pane_current_command}|#{pane_current_path}' 2>&1
pgrep -af 'python|uvicorn|llama|node' 2>/dev/null | cut -c1-220

sec "C. HOW EACH SERVICE IS LAUNCHED (launcher lines only)"
for F in "$HOME/block1_services.sh" "$HOME/lousta_up.sh" "$HOME/qwen_keepalive.sh" "$HOME/run_base_ui2.sh" "$HOME/live_services.py"; do
  [ -f "$F" ] || continue
  echo "--- $F ($(wc -l < "$F") lines, sha $(sha256sum "$F" | cut -c1-16))"
  grep -nE 'new-window|new-session|send-keys|nohup|python3? |uvicorn|llama-server|node |--port|PORT=|cd |kill|pkill' "$F" | cut -c1-240 | sed -E "$MASK" | head -60
done
echo "--- other launchers mentioning llama-server / 11437 / 11882"
grep -rlE 'llama-server|11437|11882' "$HOME"/*.sh "$ROOT"/*.sh "$ROOT"/*/*.sh 2>/dev/null | head -20
echo "--- model files"
find "$HOME" /storage/emulated/0/Download -maxdepth 5 -name '*.gguf' -printf '%s bytes  %p\n' 2>/dev/null | head -10

sec "D. SAFETY STATE (WO-00, read-only)"
python3 - "$ROOT" <<'PY'
import json, os, sys
R = sys.argv[1]
def load(p):
    try: return json.load(open(p))
    except Exception as e: return "UNREADABLE:%s" % type(e).__name__
A = R + "/brain_hub_v1/data/autopilot_control/"
L = R + "/loukey_v1/auto_inbox/"
for name, p in [("state.json", A+"state.json"), ("queue.json", A+"queue.json")]:
    d = load(p)
    if isinstance(d, str): print(name, d); continue
    items = d if isinstance(d, list) else (d.get("items") or d.get("queue") or d.get("cycles") or [])
    if isinstance(items, dict): items = list(items.values())
    print(name, "top_keys=", sorted(d.keys())[:15] if isinstance(d, dict) else "list")
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict):
            st = it.get("status") or it.get("state")
            if st in ("RUNNING", "QUEUED", "WAITING_OWNER_GATE", "EXECUTING") or "BR37" in str(it.get("cycle_id", it.get("id", ""))):
                print("  ", it.get("cycle_id") or it.get("id"), st)
    if isinstance(d, dict):
        for k in ("status", "state", "active", "executing", "current", "lane"):
            if k in d: print("  ", k, "=", str(d[k])[:160])
for n in ("approved_bundle.json", "error.json"):
    p = L + n
    if os.path.exists(p):
        d = load(p); print(n, "EXISTS", "mtime", int(os.path.getmtime(p)))
        if isinstance(d, dict): print("  keys=", sorted(d.keys())[:15], "| error=", str(d.get("error", ""))[:200])
    else:
        print(n, "ABSENT")
PY

sec "E. 11880 CHAT FIELD + RISKY ROUTES"
grep -n -A12 'api/chat"' "$WB/app_trainee.py" 2>/dev/null | head -30 | sed -E "$MASK"
grep -nE '@app\.(get|post)\(' "$WB/app_trainee.py" 2>/dev/null | cut -c1-140 | head -80
echo "--- external hosts in 11880 code"
grep -rhoE 'https?://[A-Za-z0-9.-]+' --include='*.py' "$WB" 2>/dev/null | grep -vE '127\.0\.0\.1|localhost' | sort | uniq -c | sort -rn | head -10
echo "--- 1182 router tmux routes"
grep -rnE 'tmux/send|send-keys|load-buffer' "$ROOT/loucorp_dashboard_v1/owner_experience_v1/self_build_control_loop_v1/promotions/1182_R4_RESERVED_SHELL_CANDIDATE_20260925_084929/runtime/" 2>/dev/null | cut -c1-200 | head -10

sec "F. DOWNLOADS: BLUEBOT PROJECTS"
for D in /storage/emulated/0/Download "$HOME/storage/downloads"; do
  [ -d "$D" ] && { DL="$D"; break; }
done
if [ -z "$DL" ]; then
  echo "DOWNLOADS_NOT_READABLE (run: termux-setup-storage, allow, then re-run)"
else
  echo "DOWNLOADS=$DL"
  echo "--- by type (all files)"
  find "$DL" -maxdepth 3 -type f 2>/dev/null | sed -E 's/.*\.([A-Za-z0-9]{1,6})$/\1/;t;s/.*/(none)/' | tr 'A-Z' 'a-z' | sort | uniq -c | sort -rn | head -15
  echo "--- BlueBot-related files, newest first (date | size | name)"
  find "$DL" -maxdepth 4 -type f \( -iname '*bluebot*' -o -iname '*lousta*' -o -iname '*loubot*' -o -iname '*loucode*' \
       -o -iname '*loukey*' -o -iname '*loucorp*' -o -iname '*1182*' -o -iname '*11880*' -o -iname '*approvalpad*' \
       -o -iname '*handover*' -o -iname '*manifest*' -o -iname '*swarm*' -o -iname '*workbench*' -o -iname '*termux*' \) \
       -printf '%TY-%Tm-%Td %TH:%TM | %8s | %P\n' 2>/dev/null | sort -r | head -200
  echo "--- archives (sha256 prefix)"
  find "$DL" -maxdepth 3 -type f \( -iname '*.tar.gz' -o -iname '*.tgz' -o -iname '*.zip' \) \
       \( -iname '*bluebot*' -o -iname '*lousta*' -o -iname '*loubot*' -o -iname '*lou*' \) 2>/dev/null | head -40 |
    while read -r F; do printf '%s  %s\n' "$(sha256sum "$F" | cut -c1-16)" "${F#$DL/}"; done
  echo "--- BlueBot folders"
  find "$DL" -maxdepth 2 -type d \( -iname '*bluebot*' -o -iname '*lousta*' -o -iname '*loubot*' -o -iname '*lou*' \) \
       -printf '%TY-%Tm-%Td | %p\n' 2>/dev/null | sort -r | head -40
fi

sec "G. LATEST HANDOVERS IN THE SPINE"
ls -t "$ROOT/session_handovers" 2>/dev/null | head -5
ls -t "$ROOT/supervised_dev" 2>/dev/null | head -15

echo
echo "FILES_CHANGED=NO (except this report)  SERVICES_CHANGED=NO"
} 2>&1 | sed -E "$MASK" | sed -E "$MASK2" > "$OUT"

cp "$OUT" /storage/emulated/0/Download/ 2>/dev/null && WHERE="Downloads/$(basename "$OUT")" || WHERE="$OUT"
printf '\033[32mCENSUS_DONE\033[0m  lines=%s\n' "$(wc -l < "$OUT")"
echo "REPORT=$OUT"
echo "UPLOAD_THIS=$WHERE"
