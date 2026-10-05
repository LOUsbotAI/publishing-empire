# BlueBot team build charter: finishing the Lousta app

**Owner:** Louie · **App:** Lousta Hub `127.0.0.1:11082` · **Team entry:** BlueBot `127.0.0.1:11880`
**State:** `PRODUCTION=LOCKED · SELF_APPROVAL=NO · MAX_EXECUTING=1 · BRAIN=SUGGEST_ONLY`

## How the team builds the rest of the app
```text
Louie opens Build tab → taps "Hand to BlueBot" on a work order → reviews the brief → Send
      ↓
BlueBot (11880) → Engineering → LouCode drafts ONE module file
      ↓
Team runs tools/check_module.py → reports file, sha256, real data sample
      ↓
Candidate waits in $ROOT/supervised_dev/hub_modules/<name>/   (nothing is live yet)
      ↓
Louie reviews → bash PROMOTE_MODULE.sh <file> [tile]          (owner gate)
      ↓
Hub reloads → new native screen → mark the work order DONE in work_orders.json
```

## What the team may and may not do
| May | May not |
|---|---|
| Read services with `api.get` (GET, local, through the hub) | `fetch`, POST/PUT/DELETE, WebSocket |
| Draft module files as candidates | Copy files into the hub, edit `modules.json`, restart services |
| Put text in Louie's chat box with `api.ask` | Send messages, approve gates, run cycles |
| Propose new read-only routes | Build new routes, queues, runners, tmux sessions |
| Report what could not be verified | Guess JSON keys or invent data |

The hub enforces most of this itself:
- `/hub/get` reads only ports listed under `health`, and never 11884.
- `/hub/chat` is the hub's only write.
- `check_module.py` holds any module that tries anything else.

## Order of work
`WO-00` (Louie: safety checks) → `WO-01` (census, read-only) → `WO-02..07` (one module each, any order)
→ `WO-08` (chat labels) → `WO-09` (phone QA) → `WO-10` (retire framed pages).

## Definition of done for the app
- Every Core and Observe tile is a native module, or a framed page Louie chose to keep.
- Chat shows the department and trace for each reply.
- Phone QA passes in both themes and with keyboard only.
- Live 1182, Owner Gate semantics, BR37N2 and the production lock are unchanged.
