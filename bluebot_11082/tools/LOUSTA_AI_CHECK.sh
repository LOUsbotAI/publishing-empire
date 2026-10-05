#!/data/data/com.termux/files/usr/bin/bash
# LOUSTA AI CHECK: LouCode, AutoCode, Swarm, local LLM (llama 11438 / Qwen 11437) and LouBot.
# READ-ONLY, except two tiny test prompts sent to the LOCAL model (127.0.0.1 only).
# Starts, stops, edits nothing. Never touches 11884. Secrets masked.
# Optional: bash LOUSTA_AI_CHECK.sh --chat   also sends one "ping" through BlueBot /api/chat (same as typing in chat).
export PATH="/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/bin/applets"
ROOT="$HOME/bluebits/empire_director_v1"
WB="$ROOT/supervised_dev/1182_bluebot_chat_installation_ready_v1/BLUEBOT_CHAT_INSTALLATION_READY_V1_20260926T020840Z/workbench"
STAMP="$(date +%Y%m%d_%H%M%S)"; OUT="$HOME/LOUSTA_AI_CHECK_$STAMP.txt"
MASK='s/((api[_-]?key|token|secret|password|authorization)[A-Za-z0-9_-]*["'"'"']?[=: ]+["'"'"']?)[^ "'"'"',}]+/\1***MASKED***/Ig; s/(Bearer[[:space:]]+)[^ "'"'"',}]+/\1***MASKED***/Ig; s/\b(sk-|xai-|gsk_|ghp_|AIza|hf_)[A-Za-z0-9_-]{6,}/\1***MASKED***/g'
declare -A RES
res(){ RES["$1"]="$2"; printf '  >> %-22s %s\n' "$1" "$2"; }
sec(){ printf '\n==================== %s ====================\n' "$1"; }
code(){ curl -s -o /dev/null --connect-timeout 2 --max-time "${2:-4}" -w '%{http_code}' "$1" 2>/dev/null; }

{
echo "LOUSTA AI CHECK $STAMP   MUTATION=NO RESTART=NO 11884=NOT_TOUCHED PRODUCTION=LOCKED"
echo "ANDROID=$(getprop ro.build.version.release 2>/dev/null)  RAM: $(free -m 2>/dev/null | awk '/Mem:/{print $2" MB total, "$7" MB available"}')"

sec "1. LLAMA-SERVER 11438"
pgrep -af 'llama-server|llama_server' | cut -c1-260 || echo "NO_LLAMA_PROCESS"
C=$(code http://127.0.0.1:11438/health); echo "health=HTTP_${C:-000}"
curl -s --max-time 4 http://127.0.0.1:11438/v1/models 2>/dev/null | head -c 400; echo
echo "--- model files"; find "$HOME" /storage/emulated/0/Download -maxdepth 6 -name '*.gguf' -printf '%s bytes  %p\n' 2>/dev/null | head -10
echo "--- llama binary"; command -v llama-server 2>/dev/null || find "$HOME" -maxdepth 5 -type f -name 'llama-server' 2>/dev/null | head -3
echo "--- how it is launched"; grep -rhnE 'llama-server' "$HOME"/*.sh "$ROOT"/*.sh "$ROOT"/*/*.sh 2>/dev/null | cut -c1-260 | head -8
echo "--- last log lines"; for L in "$HOME"/llama_11438*.log; do [ -f "$L" ] && { echo "[$L]"; tail -n 6 "$L"; }; done
if [ "$C" = "200" ]; then
  T0=$(date +%s); R=$(curl -s --max-time 120 http://127.0.0.1:11438/v1/chat/completions -H 'Content-Type: application/json' \
    -d '{"messages":[{"role":"user","content":"Reply with exactly: OK"}],"max_tokens":8,"temperature":0}' 2>/dev/null)
  echo "llama answer ($(( $(date +%s)-T0 ))s): $(echo "$R" | head -c 300)"
  echo "$R" | grep -q '"content"' && res "llama 11438" "PASS (answers)" || res "llama 11438" "UP but no answer"
else res "llama 11438" "DOWN"; fi

sec "2. QWEN ADAPTER 11437"
pgrep -af 'local_qwen_openai_adapter|qwen' | cut -c1-200 || echo "NO_QWEN_ADAPTER_PROCESS"
M=$(curl -s --max-time 4 http://127.0.0.1:11437/v1/models 2>/dev/null); echo "models: $(echo "$M" | head -c 300)"
MODEL=$(echo "$M" | python3 -c 'import json,sys;d=json.load(sys.stdin);print((d.get("data") or [{}])[0].get("id",""))' 2>/dev/null)
tail -n 5 "$HOME/qwen_11437.log" 2>/dev/null
if [ -n "$M" ]; then
  T0=$(date +%s); R=$(curl -s --max-time 120 http://127.0.0.1:11437/v1/chat/completions -H 'Content-Type: application/json' \
    -d "{\"model\":\"${MODEL:-qwen}\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly: OK\"}],\"max_tokens\":8,\"temperature\":0}" 2>/dev/null)
  echo "qwen answer ($(( $(date +%s)-T0 ))s): $(echo "$R" | head -c 300)"
  echo "$R" | grep -q '"content"' && res "qwen 11437" "PASS (answers)" || res "qwen 11437" "UP but no answer"
else res "qwen 11437" "DOWN"; fi
echo "--- keepalive"; pgrep -af qwen_keepalive | head -2; head -30 "$HOME/qwen_keepalive.sh" 2>/dev/null | grep -nE 'curl|sleep|11437|11438|llama' | head -8

sec "3. LOUBOT / BLUEBOT 11880"
C=$(code http://127.0.0.1:11880/api/status); echo "11880 status=HTTP_${C:-000}"
curl -s --max-time 4 http://127.0.0.1:11880/api/status 2>/dev/null | head -c 500; echo
echo "--- which model 11880 uses"; grep -nE '11437|11438|MODEL|model_name|grok|x\.ai' "$WB/app_trainee.py" 2>/dev/null | cut -c1-160 | head -15
echo "--- loubot GET routes"; grep -nE '@app\.get\("/api/(loubot|live|trainees|models|agents)' "$WB/app_trainee.py" 2>/dev/null | cut -c1-140 | head -12
for P in /api/live /api/loubot/status /api/models /api/trainees; do echo "GET $P -> HTTP_$(code http://127.0.0.1:11880$P)"; done
echo "--- LouBot folders"; ls -d "$HOME"/LouBot "$HOME"/loubot_v1 "$HOME"/loubot-sandbox 2>/dev/null
C18=$(code http://127.0.0.1:18097/); echo "LouBot ApprovalPad 18097=HTTP_${C18:-000}"
[ "$C" = "200" ] && res "loubot 11880" "PASS (up)" || res "loubot 11880" "DOWN"
if [ "$1" = "--chat" ] && [ "$C" = "200" ]; then
  T0=$(date +%s); R=$(curl -s --max-time 180 http://127.0.0.1:11880/api/chat -H 'Content-Type: application/json' -d '{"message":"ping: reply with one short line saying which model answered","source":"ai_check"}' 2>/dev/null)
  echo "chat ping ($(( $(date +%s)-T0 ))s): $(echo "$R" | head -c 500)"
  [ -n "$R" ] && res "bluebot chat" "PASS (replied)" || res "bluebot chat" "NO REPLY"
fi

sec "4. LOUCODE"
grep -nE 'loucode' "$WB/app_trainee.py" 2>/dev/null | grep -E '@app\.' | cut -c1-140 | head -8
ls -la "$HOME"/loucode "$HOME"/loucode_max.py "$HOME"/loucode_decoder_patch.py 2>/dev/null | head -10
find "$ROOT" -maxdepth 4 -iname '*loucode*' -printf '%TY-%Tm-%Td %p\n' 2>/dev/null | sort -r | head -12
grep -rlE '11437|11438|qwen|llama' "$HOME"/loucode* "$HOME"/loucode 2>/dev/null | head -5 | sed 's/^/uses local LLM: /'
N=$(find "$ROOT" "$HOME" -maxdepth 4 -iname '*loucode*' 2>/dev/null | wc -l)
[ "$N" -gt 0 ] && res "loucode" "FOUND ($N files)" || res "loucode" "NOT FOUND"

sec "5. AUTOCODE"
ls -d "$HOME"/auto-loucode "$HOME"/auto_publish 2>/dev/null
find "$ROOT" "$HOME/auto-loucode" -maxdepth 4 \( -iname '*autocode*' -o -iname '*auto_code*' -o -iname '*auto-loucode*' \) -printf '%TY-%Tm-%Td %p\n' 2>/dev/null | sort -r | head -12
ls "$HOME/auto-loucode" 2>/dev/null | head -15
grep -rlE '11437|11438|qwen|llama' "$HOME/auto-loucode" 2>/dev/null | head -5 | sed 's/^/uses local LLM: /'
N=$(find "$ROOT" "$HOME/auto-loucode" -maxdepth 4 \( -iname '*autocode*' -o -iname '*auto-loucode*' -o -iname '*auto_code*' \) 2>/dev/null | wc -l)
[ "$N" -gt 0 ] || [ -d "$HOME/auto-loucode" ] && res "autocode" "FOUND" || res "autocode" "NOT FOUND"

sec "6. SWARM (Manager V2, Brain Challenger V2, G1, bindings)"
CT="$ROOT/core_team_upgrade_v1"
for F in \
  "$CT/composite_team_upgrade_04/qualifications/LOUSTA_CORE_SWARM_BOUNDED_AUTONOMY_CURRENT.json" \
  "$CT/swarm_core_v1/bindings/BLUEBOT_MANAGER_V2_SWARM_BINDING_V1.json" \
  "$CT/swarm_core_v1/bindings/BRAIN_CHALLENGER_V2_SWARM_BINDING_V1.json" \
  "$CT/brain_challenger_v2/qualified_bindings/BRAIN_CHALLENGER_V2_03C_CURRENT.json" \
  "$CT/bluebot_manager_v2/qualified_bindings/BLUEBOT_MANAGER_V2_CORE_TEAM_BUILD_BINDING_V1.json"; do
  [ -f "$F" ] && printf 'OK   %s  %s\n' "$(sha256sum "$F" | cut -c1-12)" "${F#$ROOT/}" || printf 'MISS %s\n' "${F#$ROOT/}"
done
python3 - "$CT/composite_team_upgrade_04/qualifications/LOUSTA_CORE_SWARM_BOUNDED_AUTONOMY_CURRENT.json" <<'PY' 2>/dev/null
import json,sys
d=json.load(open(sys.argv[1]))
for k in ("status","state","graduated","bounded_autonomy","authority","brain_authority","max_executing","self_approval","production"):
    if k in d: print("  ",k,"=",str(d[k])[:120])
PY
echo "--- swarm processes"; pgrep -af 'swarm|manager|brain|g1_|pm2' | grep -v pgrep | cut -c1-180 | head -10
ls "$ROOT"/pm2_swarm.config.js "$ROOT"/.bluebot_core_swarm_canary_* 2>/dev/null
echo "--- which LLM the swarm calls"; grep -rhoE '127\.0\.0\.1:(11437|11438|6205|11904)[^"'"'"' ]*' "$CT" 2>/dev/null | sort | uniq -c | sort -rn | head -8
C6=$(code http://127.0.0.1:6205/health); C9=$(code http://127.0.0.1:11904/); echo "Brain hub 6205=HTTP_${C6:-000}  Team bus 11904=HTTP_${C9:-000}"
M=$(ls "$CT/swarm_core_v1/bindings/"*.json 2>/dev/null | wc -l)
[ "$M" -gt 0 ] && res "swarm bindings" "FOUND ($M)" || res "swarm bindings" "MISSING"
[ "${C6:-000}" != "000" ] && res "brain hub 6205" "UP" || res "brain hub 6205" "DOWN"

sec "SUMMARY"
for K in "llama 11438" "qwen 11437" "loubot 11880" "bluebot chat" "loucode" "autocode" "swarm bindings" "brain hub 6205"; do
  [ -n "${RES[$K]}" ] && printf '%-18s %s\n' "$K" "${RES[$K]}"
done
} 2>&1 | sed -E "$MASK" | tee "$OUT"

cp "$OUT" /storage/emulated/0/Download/ 2>/dev/null && echo "UPLOAD_THIS=Downloads/$(basename "$OUT")" || echo "REPORT=$OUT"
