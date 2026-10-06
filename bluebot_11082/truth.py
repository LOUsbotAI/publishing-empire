"""LOUSTA TRUTH: Termux is the source of truth. This module reads it (never changes it) and
returns one verified snapshot that the app shows and every brain/brief receives.

Read-only facts: services (GET), tmux windows, key processes, BlueBot runtime status, autopilot
state/queue (BR37N2), LouKey inbox (approved bundle, error), the execution lock, free memory,
and the canonical file hashes from truth_manifest.json (MATCH / DRIFT / MISSING).
Subprocess use is limited to fixed read-only commands: tmux list-windows, pgrep, getprop.
"""
import hashlib
import json
import os
import subprocess
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SOCK = "lousta-bluebot-studio"
PROCS = {
    "llama-server": "llama-server",
    "qwen adapter": "local_qwen_openai_adapter",
    "bluebot 11880": "uvicorn.*1188|app_trainee|11880",
    "loukey runner": "loukey_real_auto_runner",
    "queue controller": "loubot_bounded_work_queue_controller",
    "supervisor": "bluebot_auto_supervisor",
}
_cache = {"t": 0, "data": None}
_lock = threading.Lock()
_sha_cache = {}


def _run(args, timeout=3):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def _json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return "MISSING"
    except Exception as e:
        return "UNREADABLE:" + type(e).__name__


def _sha(path):
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return None
    key = (path, st.st_mtime, st.st_size)
    if key not in _sha_cache:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        _sha_cache[key] = h.hexdigest()
    return _sha_cache[key]


def _get_json(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read(200000).decode("utf-8", "replace"))
    except Exception:
        return None


def _items(q):
    if isinstance(q, list):
        return q
    if isinstance(q, dict):
        for k in ("items", "queue", "cycles", "requests"):
            v = q.get(k)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                return list(v.values())
    return []


def collect(cfg, health_fn):
    m = _json(os.path.join(HERE, "truth_manifest.json"))
    root = os.path.expanduser(m.get("root", "~/bluebits/empire_director_v1")) if isinstance(m, dict) else os.path.expanduser("~/bluebits/empire_director_v1")
    ac = os.path.join(root, "brain_hub_v1/data/autopilot_control")
    inbox = os.path.join(root, "loukey_v1/auto_inbox")
    t = {"ts": int(time.time()), "platform": {}, "services": [], "tmux": [], "processes": {}, "bluebot": None,
         "autopilot": {}, "loukey": {}, "files": [], "watch": [], "checks": []}

    # platform
    mem = {}
    try:
        for line in open("/proc/meminfo"):
            k, v = line.split(":", 1)
            mem[k] = int(v.split()[0]) // 1024
    except Exception:
        pass
    t["platform"] = {"android": _run(["getprop", "ro.build.version.release"]) or "?", "mem_total_mb": mem.get("MemTotal"),
                     "mem_available_mb": mem.get("MemAvailable"), "termux_prefix": os.environ.get("PREFIX", "")}

    # services, tmux, processes
    t["services"] = health_fn()
    out = _run(["tmux", "-L", SOCK, "list-windows", "-a", "-F", "#{session_name}|#{window_index}|#{window_name}|#{pane_current_command}|#{pane_dead}"])
    t["tmux"] = [dict(zip(("session", "index", "name", "cmd", "dead"), l.split("|"))) for l in out.splitlines() if l]
    for label, pat in PROCS.items():
        lines = [l for l in _run(["pgrep", "-af", pat]).splitlines() if "pgrep" not in l]
        t["processes"][label] = len(lines)

    # bluebot runtime
    t["bluebot"] = _get_json("http://127.0.0.1:11880/api/status")

    # autopilot + BR37N2
    st, q = _json(os.path.join(ac, "state.json")), _json(os.path.join(ac, "queue.json"))
    counts, active, br = {}, [], None
    for it in _items(q):
        if not isinstance(it, dict):
            continue
        s = str(it.get("status") or it.get("state") or "?")
        counts[s] = counts.get(s, 0) + 1
        cid = str(it.get("cycle_id") or it.get("id") or "")
        if s in ("RUNNING", "QUEUED", "EXECUTING"):
            active.append(cid + ":" + s)
        if "BR37N2" in cid:
            br = s
    t["autopilot"] = {"state": {k: st.get(k) for k in list(st)[:8]} if isinstance(st, dict) else st,
                      "queue_counts": counts, "active": active, "br37n2": br,
                      "global_lock_present": os.path.exists(os.path.join(ac, "queue.global_max.lock"))}

    # loukey inbox
    b, e = _json(os.path.join(inbox, "approved_bundle.json")), _json(os.path.join(inbox, "error.json"))
    t["loukey"] = {"approved_bundle": ("absent" if b == "MISSING" else
                                       {"requests": len(b.get("requests", [])) if isinstance(b, dict) else "?",
                                        "owner_approved": b.get("owner_approved") if isinstance(b, dict) else None}),
                   "error": None if e == "MISSING" else (str(e.get("error", e))[:240] if isinstance(e, dict) else str(e)[:240]),
                   "error_age_min": (int((time.time() - os.path.getmtime(os.path.join(inbox, "error.json"))) / 60)
                                     if os.path.exists(os.path.join(inbox, "error.json")) else None)}

    # canonical files
    if isinstance(m, dict):
        for f in m.get("pinned", []):
            got = _sha(os.path.join(root, f["path"]))
            t["files"].append({"name": f["name"], "path": f["path"],
                               "state": "MISSING" if got is None else ("MATCH" if got == f["sha256"] else "DRIFT"),
                               "sha": (got or "")[:16], "expected": f["sha256"][:16]})
        for f in m.get("watch", []):
            got = _sha(os.path.join(root, f["path"]))
            t["watch"].append({"name": f["name"], "state": "MISSING" if got is None else "PRESENT", "sha": (got or "")[:16]})

    # checks (invariants)
    def check(name, ok, detail):
        t["checks"].append({"name": name, "state": "PASS" if ok is True else ("FAIL" if ok is False else "WARN"), "detail": detail})
    bb = t["bluebot"] or {}
    check("Production locked", bb.get("production") == "LOCKED" if bb else None, "11880 reports production=" + str(bb.get("production")))
    runners = t["processes"].get("loukey runner", 0)
    check("At most one execution (MAX_EXECUTING=1)", runners <= 1 and len(active) <= 1, "%d runner process(es), %d active cycle(s)" % (runners, len(active)))
    if runners or active:
        check("Execution lock held while running", t["autopilot"]["global_lock_present"], "queue.global_max.lock " + ("present" if t["autopilot"]["global_lock_present"] else "MISSING during a run"))
    check("BR37N2 preserved", (br in (None, "WAITING_OWNER_GATE")) if br else None, "BR37N2=" + str(br))
    check("BlueBot reasoner up", bool(bb.get("reasoner")) if bb else False, "reasoner=%s chat=%s" % (bb.get("reasoner"), bb.get("chat_runtime_state")))
    drift = [f["name"] for f in t["files"] if f["state"] != "MATCH"]
    check("Canonical files match manifest", not drift, ("drift/missing: " + ", ".join(drift[:6])) if drift else "%d files match" % len(t["files"]))
    dead = [w["name"] for w in t["tmux"] if w.get("dead") == "1"]
    check("No dead tmux windows", not dead, ", ".join(dead) if dead else "%d windows alive" % len(t["tmux"]))
    age = t["loukey"]["error_age_min"]
    if t["loukey"]["error"] and age is not None and age < 60:
        check("No recent LouKey error", False, "%s (%d min ago)" % (t["loukey"]["error"][:120], t["loukey"]["error_age_min"]))
    mem_ok = (t["platform"]["mem_available_mb"] or 0) >= 1500
    check("Enough free memory for the local model", mem_ok if t["platform"]["mem_available_mb"] else None, "%s MB available" % t["platform"]["mem_available_mb"])
    t["summary"] = {k: sum(1 for c in t["checks"] if c["state"] == k) for k in ("PASS", "WARN", "FAIL")}
    return t


def snapshot(cfg, health_fn, max_age=10):
    with _lock:
        if _cache["data"] and time.time() - _cache["t"] < max_age:
            return _cache["data"]
    data = collect(cfg, health_fn)
    with _lock:
        _cache.update(t=time.time(), data=data)
    return data


def as_text(t, limit=2200):
    """Compact facts block for brains and briefs."""
    if not t:
        return ""
    up = [s["role"] + ":" + str(s["port"]) for s in t["services"] if s.get("state") == "UP"]
    down = [s["role"] + ":" + str(s["port"]) for s in t["services"] if s.get("state") != "UP"]
    bb = t.get("bluebot") or {}
    ap = t.get("autopilot", {})
    lines = [
        "LIVE TERMUX FACTS (read from the phone %s, verified by the 11082 hub):" % time.strftime("%H:%M:%S", time.localtime(t["ts"])),
        "- Platform: Android %s, Termux (no root, no systemd, no sudo, no apt-get; use pkg). Services run as processes in tmux socket '%s' (windows: %s)." % (
            t["platform"].get("android"), SOCK, ", ".join(w["name"] for w in t["tmux"]) or "none"),
        "- Check things with: curl -s http://127.0.0.1:PORT/..., pgrep -af NAME, tmux -L %s list-windows. Never systemctl/service/sudo." % SOCK,
        "- Up: " + (", ".join(up) or "none") + ". Down: " + (", ".join(down) or "none") + ".",
        "- BlueBot 11880: reasoner=%s chat=%s runtime=%s production=%s." % (bb.get("reasoner"), bb.get("chat_runtime_state"), bb.get("runtime_state"), bb.get("production")),
        "- Autopilot: queue %s; active %s; BR37N2=%s; execution lock %s." % (ap.get("queue_counts"), ap.get("active") or "none", ap.get("br37n2"), "present" if ap.get("global_lock_present") else "absent"),
        "- LouKey: bundle %s; last error: %s." % (t["loukey"].get("approved_bundle"), t["loukey"].get("error") or "none"),
        "- Checks: " + "; ".join("%s=%s" % (c["name"], c["state"]) for c in t["checks"]),
        "- Memory: %s MB free of %s MB." % (t["platform"].get("mem_available_mb"), t["platform"].get("mem_total_mb")),
        "- Rules: PRODUCTION=LOCKED, SELF_APPROVAL=NO, MAX_EXECUTING=1, Brain=SUGGEST_ONLY, 11884 owner-manual only. Owner (Louie) approves every live action.",
    ]
    return "\n".join(lines)[:limit]
