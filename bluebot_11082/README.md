# Lousta Hub 11082

One screen at `http://127.0.0.1:11082/` that brings all the separate BlueBot pages together.

- **Bottom bar:** `Chat | Code | Work | Build | More` (R4.0 rule).
- **More:** searchable, grouped: Core, Control & Gate, Observe, Business & Control,
  Social & Channels, LOUCORP (Future).
- **Health pill:** live up/down for 1182, 11880, 11770, 11883, 18082, 18097, 1185, 11902, 6205, 11437, 11438.
- Each page loads in its own frame **straight from its own port**, so it keeps its own buttons and rules.
  Switching tabs keeps each page alive. Offline services show a placeholder instead of a broken frame.
- Social and LOUCORP tiles are **PLANNED / NOT CONNECTED**. They load nothing.

## Safety contract
| Item | Value |
|---|---|
| Bind | 127.0.0.1 only |
| Methods | GET/HEAD only. POST/PUT/PATCH/DELETE → 405 |
| Execution | None. No subprocess, tmux, 11884, `/api/tmux/send`, `run-approved`, `/loukey/auto` |
| Live 1182 | Untouched |
| Health probes | Server-side GET, 127.0.0.1 URLs only, 2s timeout |

## Install on the phone
```bash
cd ~/publishing-empire && git pull origin claude/new-session-r4mni9
bash ~/publishing-empire/bluebot_11082/STAGE_11082.sh      # copies to supervised_dev, starts nothing
bash <CANDIDATE_ROOT>/START_11082.sh                        # new window in existing studio tmux
```
Stop: `tmux -L lousta-bluebot-studio kill-window -t hub11082`. Rollback: delete the candidate folder.

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
