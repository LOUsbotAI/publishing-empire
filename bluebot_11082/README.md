# Lousta Hub 11082

One modern app at `http://127.0.0.1:11082/` that brings all the separate BlueBot pages together.

- **Chat v2 (Claude/ChatGPT style):**
  - **Multi-bot:** BlueBot, Grok and Grok Image, picked from the bot chip. Add more in `modules.json` → `bots`.
  - **Conversations:** saved on the phone.
  - **Replies:** formatted text with copy buttons on code, plus Stop, Retry and Speak.
  - **Voice:** dictation fills the box and never sends by itself.
  - **Bot colours:** every bot has its own colour and icon on its message boxes (`color` and `icon` in `modules.json` → `bots`).
  - **Group chat:** pick 2+ bots in the bot sheet. Each answers in turn and sees the others' replies. **↻ Let them continue** runs one more bot-to-bot round. It never loops on its own.
  - **Talk mode** (wave button): hands-free voice. You speak, it sends, each bot answers aloud in its own voice, then it listens again. Say "stop" or tap **End talk**. This is the only place a message sends without tapping Send. Chat only; nothing runs. Needs Chrome speech recognition, which uses Google's speech service.
  - **Screen:** one-frame snapshot on desktop, or a screenshot from the gallery on a phone.
  - **Live Termux:** read-only panel.
  - **Command palette:** Ctrl/⌘+K.
- **Code tab: Termux script loop.**
  1. Describe the task and pick a coding bot. **Write script** returns one Termux-ready bash script.
  2. The app checks it before you copy it and rates it **READ ONLY / MUTATES / DANGER**. It flags:
     - sudo
     - `rm -rf` on home or root
     - `curl | bash`
     - 11884 or gate paths
     - `set -e` or `exit` at the top level
     - nano
     - pkill
     - new tmux sessions
     - heredocs that are never closed
  3. You run it in Termux, then paste the output or tap **Pull from Termux** (read-only 11883, once configured). Error lines are counted.
  4. **Fix & next input** sends the script and its output to the fixer agent. It replies with the ROOT CAUSE and a corrected script, or DONE plus the next step. Every round is kept (v1, Fix 1, Fix 2…), up to 8.
  5. **Auto-fix when output arrives** watches Live Termux for the script's PASTE END and runs the fix round for you. It never runs anything in Termux; you always paste and run.
- **Build → Auto-build run:** tick READY work orders and pick a bot (Grok by default). They're sent one at a time while you watch, at most 5 per run. It stops on the first failure or when you press Stop. Replies are drafts; nothing goes live without `PROMOTE_MODULE.sh`.
- **Chat is native.** Messages go to the existing BlueBot chat route (11880 `/api/chat`). It's the same behaviour 1182 chat already has.
- **Everything (More):** health dashboard plus every page, grouped and searchable.
- **Older pages** open full screen in a clean viewer with Back, Reload and Open. You never get two nav bars.
- Dark and light themes. The phone setting is followed until you tap the moon.

- **Bottom bar:** `Chat | Code | Work | Build | More` (R4.0 rule). Code/Work open LouCode and Workbench. Build is the team's work queue.
- **More:** searchable, grouped: Core, Control & Gate, Observe, Business & Control,
  Social & Channels, LOUCORP (Future).
- **Health pill:** live up/down for 1182, 11880, 11770, 11883, 18082, 18097, 1185, 11902, 6205, 11437, 11438.
- Each page loads in its own frame **straight from its own port**, so it keeps its own buttons and rules.
  Switching tabs keeps each page alive. Offline services show a placeholder instead of a broken frame.
- Social and LOUCORP tiles are **PLANNED / NOT CONNECTED**. They load nothing.

## Step 0: census (read-only, run this first)
```bash
bash ~/publishing-empire/bluebot_11082/tools/LOUSTA_CENSUS.sh
```
It collects:
- live ports (including 11882)
- tmux windows
- how each service is launched
- model files
- safety state (WO-00)
- the 11880 chat field and risky routes
- your Downloads BlueBot projects

It changes nothing and never touches 11884. Secrets are masked. The report is copied to Downloads, ready to upload.

## Connect everything (the last bit)
```bash
python3 ~/publishing-empire/bluebot_11082/tools/lousta_connect.py          # scans 1024-20000 for every local page (add --no-scan to skip)
```
It finds the running hub and checks what answers on the phone (GET only). It works out:
- the 11883 Live Termux route
- BlueBot's chat and image fields
- every `@bot` BlueBot knows, each given its own colour and icon
- your coding agents that serve a page, added as tiles under **Agents**
- **the features inside every local web page**: it reads each page's own menu (links, tabs and section buttons such as 1182's Command, Live, Work, Warehouse, Chat, Projects, Outputs) and adds one tile per feature under a section named after that page

It shows the proposed changes and writes `modules.json` only after you type **y**, keeping a backup and printing a rollback line. Re-run it whenever you start more services. It never POSTs, restarts anything or touches 11884.

## AI stack check (LouCode, AutoCode, Swarm, Qwen/llama, LouBot)
```bash
bash ~/publishing-empire/bluebot_11082/tools/LOUSTA_AI_CHECK.sh          # add --chat to also ping BlueBot
```
Read-only. The only thing it sends is two tiny "Reply with exactly: OK" prompts to the local model on 127.0.0.1. It ends with a PASS/DOWN summary and copies the report to Downloads.

## Multi-brain: BlueBot never stops
BlueBot (11880) answers first. If it **times out (45 s), errors or returns nothing**, the hub tries the next brain in `modules.json` → `brains.order`:

1. BlueBot
2. Qwen (local 11437)
3. llama (local 11438)
4. Grok
5. Claude
6. OpenAI
7. Gemini
8. OpenRouter
9. Groq

The reply is labelled, e.g. **BlueBot → Qwen (local) (backup)** with `FALLBACK · Qwen (local)`.

- **Keys:** `mkdir -p ~/.lousta && cp keys.env.example ~/.lousta/keys.env && chmod 600 ~/.lousta/keys.env`, then fill in only the ones you have (plus the model name for each). Remote brains without a key are skipped. Claude defaults to `claude-opus-5-5`.
- Keys stay in that file. They're never sent to the browser, written to logs or committed (`.gitignore` covers them). **System → Brains** shows each brain's state as "key set", "needs …" or "local", never the key.
- Recent chat history goes only to backup brains so they have context. BlueBot receives exactly what it did before.
- Backup brains are **chat only**: no tools, no commands, no approvals. Their answers are drafts like any other.
- New bots: **Brain** (suggest-only), **Engineering** and **LouCode** go through BlueBot's departments. **Claude** and **Qwen (local)** talk straight to that brain and fall back if it fails.
- Turn fallback off with `"brains": {"fallback": false}`.

## Make BlueBot build the rest (one tap)
**Build → ▶ Build the rest** sends BlueBot the next ready work orders, up to 5 per tap, one at a time while you watch.
- It respects order: WO-01 (census) goes first; WO-02 to WO-07 and WO-11 to WO-14 follow once WO-01 is in Review or Done.
- Each brief gets **real data just fetched** from your services (status, live, gate, readback…), so BlueBot uses real keys instead of guessing. It's also told the exact module name.
- Progress per order is saved on the phone: READY → IN PROGRESS → REVIEW → DONE (**Mark done** / **Reopen**).
- Every BlueBot reply that contains a module gets **Check** (same rules as `check_module.py`), **Save .js** (to Downloads) and **Copy promote command**. Paste that command in Termux to put it live, then reload the app.
- New orders: **WO-11 Warehouse**, **WO-12 Projects**, **WO-13 Outputs · Hold** (1182's features, rebuilt natively) and **WO-14 Swarm console**.

## Team build (finish the app with BlueBot)
See **BUILD_CHARTER.md**. The **Build** tab lists the team's work orders (`work_orders.json`).
**Hand to BlueBot** puts a brief in the chat box, and you press Send. The team delivers one module file per work order
as a candidate. You run `bash PROMOTE_MODULE.sh <file> [tile]` to put it live. `modules/services.js` is the reference module.

## Safety contract
| Item | Value |
|---|---|
| Bind | 127.0.0.1 only |
| Methods | GET/HEAD, plus **one** write: `POST /hub/chat`, forwarded unchanged to `127.0.0.1:11880/api/chat` (64 KB max, JSON only). Every other write → 405 |
| Execution | None. No subprocess, tmux, 11884, `/api/tmux/send`, `run-approved`, `/loukey/auto` |
| Live 1182 | Untouched |
| Module reads | `GET /hub/get?u=` only to ports in `health`, never 11884, 2 MB cap, read-only |
| Team modules | Checked by `tools/check_module.py`, installed only by owner `PROMOTE_MODULE.sh` |
| Health probes | Server-side GET, 127.0.0.1 URLs only, 2s timeout |

## Install on the phone
```bash
cd ~/publishing-empire && git pull origin claude/new-session-r4mni9
bash ~/publishing-empire/bluebot_11082/STAGE_11082.sh      # copies to supervised_dev, starts nothing
bash <CANDIDATE_ROOT>/START_11082.sh                        # new window in existing studio tmux
```
Stop: `tmux -L lousta-bluebot-studio kill-window -t hub11082`. Rollback: delete the candidate folder.

## Confirm the chat message field (read-only)
The hub sends `{"message": "...", "conversation_id", "trace_id", "source"}`. If BlueBot answers
"didn't accept the message format", check which field 11880 expects:
```bash
WB="$HOME/bluebits/empire_director_v1/supervised_dev/1182_bluebot_chat_installation_ready_v1/BLUEBOT_CHAT_INSTALLATION_READY_V1_20260926T020840Z/workbench"
grep -n -B2 -A15 'api/chat"' "$WB/app_trainee.py" | head -60
```
Then set `"chat": {"message_key": "<field>"}` in `modules.json`. No restart needed.

## What still needs the census (left off on purpose until the routes are confirmed)
| Feature | Needs | Setting |
|---|---|---|
| Live Termux panel | 11883 snapshot route | `termux.readback_url` |
| Screenshots sent to bots | 11880 image field | `chat.image_key` |
| More chatbots (codefix agents, trainees) | their @names | `bots` |
| **Supervised keyboard** (BlueBot proposes, you tap to type it into Termux) | 11884 contract (Origin, header, nonce) | not built: owner-manual boundary, needs your explicit go-ahead |
| Auto navigation of other phone apps | Android accessibility/adb, not possible from a browser | separate authority system, not in this app |

## Add or change pages
Edit `modules.json`. Live tile: `{"id","label","icon","category","url":"http://127.0.0.1:<port>/..."}`.
Reserved tile: `"status":"PLANNED"` and no url. `primary:true` (max 4) puts it in the bottom bar.

Page paths came from the 2026-10-06 1182 webroot audit. If a tile shows a 404, fix its URL here.
`Build` points at `workspace.html` and `Command` at `app_v4.html`. Swap them if a different page is the real one.

## Found while building (not fixed by the hub. Need owner decision)
1. **1182 `/api/tmux/send`** typed into pane `%0` with no owner header or nonce (`ACCEPTED target %0`).
   That gets around the 11884 OWNER_MANUAL_ONLY boundary (do-not-regress rule 8).
2. **11880 `/api/loubot/release-approved → stage-approved → run-approved`** fired milliseconds apart,
   which looks like approval and execution in one action (rule 9).
   `run-approved` ran `loukey_real_auto_runner.py` from an adapter in `~/supervised_dev` and timed out after 300s.
   Check `state.json`, `queue.json`, `error.json`, `approved_bundle.json` and BR37N2.
3. 11880 runs `app_trainee:app` with a Grok lane, not the manifest's `app.py`. External network needs an owner decision.
