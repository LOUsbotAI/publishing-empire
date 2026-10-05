#!/data/data/com.termux/files/usr/bin/bash
# START LOCAL BRAIN: bring back llama-server 11438 + Qwen adapter 11437 (BlueBot's reasoner).
# Starts ONLY these two, each in its own window of the existing studio tmux. Asks first.
# Skips anything already answering. Never kills, never touches 11884, production stays locked.
# Usage: bash START_LOCAL_BRAIN.sh            (3B coder model, what BlueBot expects)
#        bash START_LOCAL_BRAIN.sh --small    (1.5B model: lighter on memory)
export PATH="/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/bin/applets"
ROOT="$HOME/bluebits/empire_director_v1"
SOCK=lousta-bluebot-studio
MODEL="$ROOT/models/qwen2.5-coder-3b-instruct-q4_k_m.gguf"; NEED_MB=2600
[ "$1" = "--small" ] && { MODEL="$ROOT/models/qwen2.5-1.5b-instruct-q4_k_m.gguf"; NEED_MB=1500; }
ADAPTER="$ROOT/supervised_dev/1182_bluebot_chat_installation_ready_v1/BLUEBOT_CHAT_INSTALLATION_READY_V1_20260926T020840Z/reasoner/local_qwen_openai_adapter.py"
LLAMA=$(command -v llama-server)
code(){ curl -s -o /dev/null --connect-timeout 1 --max-time "${2:-3}" -w '%{http_code}' "$1" 2>/dev/null; }

printf '\033[36m=== PASTE START: START LOCAL BRAIN ===\033[0m\n'
echo "SCOPE=llama 11438 + qwen adapter 11437 ONLY   KILL=NO   11884=NOT_TOUCHED   PRODUCTION=LOCKED"
SESS=$(tmux -L "$SOCK" display-message -p '#{session_name}' 2>/dev/null)
AVAIL=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo 2>/dev/null)
echo "TMUX_SESSION=${SESS:-NONE}   MEM_AVAILABLE=${AVAIL:-?}MB"
echo "LLAMA_BIN=${LLAMA:-MISSING}"
echo "MODEL=$MODEL ($( [ -f "$MODEL" ] && echo found || echo MISSING ))"
echo "ADAPTER=$ADAPTER ($( [ -f "$ADAPTER" ] && echo found || echo MISSING ))"
[ -z "$SESS" ] && { echo "HOLD=STUDIO_TMUX_NOT_FOUND (not creating a session)"; exit 1; }
[ -z "$LLAMA" ] || [ ! -f "$MODEL" ] || [ ! -f "$ADAPTER" ] && { echo "HOLD=MISSING_PIECE (see above)"; exit 1; }
echo "--- adapter settings it reads (so you can see what it expects)"
grep -nE 'add_argument|11437|11438|PORT|UPSTREAM|environ' "$ADAPTER" | cut -c1-150 | head -15
L=$(code http://127.0.0.1:11438/health); Q=$(code http://127.0.0.1:11437/v1/models)
echo "NOW: 11438=HTTP_${L:-000}  11437=HTTP_${Q:-000}"
if [ -n "$AVAIL" ] && [ "$AVAIL" -lt "$NEED_MB" ] && [ "$L" != "200" ]; then
  echo "WARN=LOW_MEMORY (${AVAIL}MB free, model wants ~${NEED_MB}MB). Close other apps, or use --small."
fi
echo
echo "WILL START:"
[ "$L" = "200" ] && echo "  llama 11438: already up, skip" || echo "  llama 11438: $LLAMA -m $(basename "$MODEL") --host 127.0.0.1 --port 11438 -c 4096 -t 4"
[ "$Q" = "200" ] && echo "  qwen 11437 : already up, skip" || echo "  qwen 11437 : python3 $(basename "$ADAPTER")   (in its own folder)"
read -r -p "Start now? [y/N] " A
[ "$A" = "y" ] || { echo "NOT STARTED. Nothing changed."; exit 0; }

if [ "$L" != "200" ]; then
  [ "${L:-000}" != "000" ] && { echo "HOLD=11438_PORT_BUSY_HTTP_$L (something else is on it)"; exit 1; }
  tmux -L "$SOCK" new-window -d -t "$SESS" -n llama11438 \
    "'$LLAMA' -m '$MODEL' --host 127.0.0.1 --port 11438 -c 4096 -t 4 2>&1 | tee -a \$HOME/llama_11438_hub.log"
  printf 'waiting for llama 11438 to load the model'
  for i in $(seq 1 90); do L=$(code http://127.0.0.1:11438/health); [ "$L" = "200" ] && break; printf '.'; sleep 2; done; echo
  echo "LLAMA_11438=HTTP_${L:-000}"
  [ "$L" = "200" ] || { echo "HOLD=LLAMA_NOT_UP: last log lines:"; tail -n 12 "$HOME/llama_11438_hub.log"; exit 1; }
fi
if [ "$Q" != "200" ]; then
  [ "${Q:-000}" != "000" ] && { echo "HOLD=11437_PORT_BUSY_HTTP_$Q"; exit 1; }
  tmux -L "$SOCK" new-window -d -t "$SESS" -n qwen11437 \
    "cd '$(dirname "$ADAPTER")' && python3 '$(basename "$ADAPTER")' 2>&1 | tee -a \$HOME/qwen_11437_hub.log"
  for i in $(seq 1 20); do Q=$(code http://127.0.0.1:11437/v1/models); [ "$Q" = "200" ] && break; sleep 1; done
  echo "QWEN_11437=HTTP_${Q:-000}"
  [ "$Q" = "200" ] || { echo "HOLD=ADAPTER_NOT_UP: last log lines:"; tail -n 12 "$HOME/qwen_11437_hub.log"; exit 1; }
fi
echo "--- test question (local, tiny)"
T0=$(date +%s)
R=$(curl -s --max-time 180 http://127.0.0.1:11437/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5-coder-3b-instruct-q4_k_m.gguf","messages":[{"role":"user","content":"Reply with exactly: OK"}],"max_tokens":8,"temperature":0}')
echo "ANSWER ($(( $(date +%s)-T0 ))s): $(echo "$R" | head -c 300)"
echo "BLUEBOT: $(curl -s --max-time 5 http://127.0.0.1:11880/api/status | head -c 200)"
tmux -L "$SOCK" list-windows -F '#{window_index}|#{window_name}|#{pane_current_command}'
echo "STOP=tmux -L $SOCK kill-window -t qwen11437 ; tmux -L $SOCK kill-window -t llama11438"
printf '\033[36m=== PASTE END: START LOCAL BRAIN ===\033[0m\n'
