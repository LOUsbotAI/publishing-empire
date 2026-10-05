#!/data/data/com.termux/files/usr/bin/bash
# Start the hub in a new WINDOW of the existing studio tmux (no new session).
export PATH="/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/bin/applets"
printf '\033[36m=== PASTE START: HUB 11082 START ===\033[0m\n'
echo "MUTATION=NO (files)"; echo "SERVICE_START=11082_ONLY"; echo "OTHER_SERVICES_TOUCHED=NO"; echo "PRODUCTION=LOCKED"
HERE="$(cd "$(dirname "$0")" && pwd)"
SOCK=lousta-bluebot-studio
C=$(curl -s -o /dev/null --max-time 2 -w '%{http_code}' http://127.0.0.1:11082/ 2>/dev/null || true)
if [ "${C:-000}" != "000" ]; then echo "HOLD=PORT_11082_IN_USE_HTTP_$C"; printf '\033[36m=== PASTE END ===\033[0m\n'; exit 1; fi
SESS=$(tmux -L "$SOCK" display-message -p '#{session_name}' 2>/dev/null)
if [ -z "$SESS" ]; then echo "HOLD=STUDIO_TMUX_NOT_FOUND (not creating a new session)"; exit 1; fi
tmux -L "$SOCK" new-window -d -t "$SESS" -n hub11082 \
  "cd '$HERE' && python3 hub_11082.py 2>&1 | tee -a \$HOME/hub_11082.log"
for i in 1 2 3 4 5 6; do
  C=$(curl -s -o /dev/null --max-time 2 -w '%{http_code}' http://127.0.0.1:11082/hub/status 2>/dev/null || true)
  [ "$C" = "200" ] && break; sleep 1
done
echo "HUB_11082=HTTP_${C:-000}"
P=$(curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:11082/hub/status 2>/dev/null || true)
echo "POST_REFUSED=$([ "$P" = "405" ] && echo PASS || echo "FAIL_HTTP_$P")"
tmux -L "$SOCK" list-windows -F '#{window_index}|#{window_name}|#{pane_current_command}'
echo "OPEN=http://127.0.0.1:11082/"
echo "STOP=tmux -L $SOCK kill-window -t hub11082"
printf '\033[36m=== PASTE END: HUB 11082 START ===\033[0m\n'
