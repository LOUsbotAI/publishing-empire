#!/usr/bin/env python3
"""LOUSTA CONNECT: wire everything already built on this phone into the 11082 app.

What it does (all local, 127.0.0.1 only):
  1. finds which services answer (GET only) - known ports + ports named in your launch scripts
  2. finds the 11883 Termux readback route that returns screen_plain  -> termux.readback_url
  3. reads BlueBot's /api/chat handler to learn the message field       -> chat.message_key / image_key
  4. reads every @name BlueBot knows (grok, codefix agents, trainees)   -> bots (own colour + icon)
  5. finds your coding agents / bots that serve a web page               -> health + "Agents" tiles
Then it SHOWS the changes and writes modules.json only if you type y (backup kept).
It never POSTs, never restarts anything, never touches 11884.
Usage: python3 lousta_connect.py [hub_dir] [--yes]
"""
import glob, json, os, re, shutil, subprocess, sys, time, urllib.request, urllib.error

HOME = os.path.expanduser("~")
ROOT = os.path.join(HOME, "bluebits/empire_director_v1")
WB = os.path.join(ROOT, "supervised_dev/1182_bluebot_chat_installation_ready_v1/BLUEBOT_CHAT_INSTALLATION_READY_V1_20260926T020840Z/workbench")
UI = os.path.join(ROOT, "supervised_dev/1182_r4_chat_integration_v1/R4_CHAT_INTEGRATION_V1_20260926/ui")
NEVER = {11884}
KNOWN = {1182: "Front door", 11880: "BlueBot", 11882: "Directory", 11770: "Owner Gate", 11883: "Readback",
         18082: "Owner Ctl", 18097: "LouBot Pad", 1185: "Honeycomb", 11902: "Proposals", 6205: "Brain Hub",
         11437: "Qwen", 11438: "llama", 11904: "Team bus", 18088: "Feed", 1183: "Readback (alt)"}
PALETTE = ["#22c55e", "#eab308", "#06b6d4", "#a855f7", "#ef4444", "#14b8a6", "#f43f5e", "#84cc16", "#0ea5e9", "#d946ef"]
ICONS = ["🛠", "⚡", "🔧", "🧪", "🧠", "📐", "🔍", "🧩", "🛰", "📦"]


def get(url, timeout=2.5):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "lousta-connect"}), timeout=timeout) as r:
            return r.status, r.read(400_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return None, ""


def read(p):
    try:
        return open(p, encoding="utf-8", errors="replace").read()
    except Exception:
        return ""


def find_hub(argv):
    for a in argv:
        if not a.startswith("--") and os.path.isfile(os.path.join(a, "modules.json")):
            return os.path.abspath(a)
    try:
        p = subprocess.run(["tmux", "-L", "lousta-bluebot-studio", "display-message", "-p", "-t", "hub11082", "#{pane_current_path}"],
                           capture_output=True, text=True, timeout=3).stdout.strip()
        if p and os.path.isfile(os.path.join(p, "modules.json")):
            return p
    except Exception:
        pass
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return here


def script_ports():
    ports = {}
    files = glob.glob(HOME + "/*.sh") + glob.glob(ROOT + "/*.sh") + glob.glob(ROOT + "/*/*.sh") + glob.glob(HOME + "/*.py")
    for f in files[:400]:
        for m in re.finditer(r"(?:--port[ =]|PORT=|:)(\d{4,5})\b", read(f)):
            p = int(m.group(1))
            if 1024 < p < 65535 and p not in NEVER:
                ports.setdefault(p, os.path.basename(f))
    return ports


def readback_route():
    src = read(os.path.join(UI, "owner_termux_readback_r8_r3.py"))
    cands = sorted(set(re.findall(r"""["'](/[A-Za-z0-9_\-/]{2,80})["']""", src)), key=len)
    cands = [c for c in cands if not re.search(r"input|send|key|text|post|write|exec", c, re.I)] + ["/", "/snapshot", "/api/snapshot", "/api/owner-termux-r8r3/snapshot"]
    seen = set()
    for c in cands:
        if c in seen:
            continue
        seen.add(c)
        code, body = get("http://127.0.0.1:11883" + c)
        if code == 200 and "screen_plain" in body:
            try:
                d = json.loads(body)
                if isinstance(d, dict) and "screen_plain" in d:
                    return "http://127.0.0.1:11883" + c, list(d.keys())[:12]
            except ValueError:
                pass
    return None, cands[:8]


def chat_fields():
    src = read(os.path.join(WB, "app_trainee.py"))
    i = src.find('"/api/chat"')
    if i < 0:
        return None, None, []
    window = src[max(0, i - 4000): i + 4000]
    keys = re.findall(r"""\.get\(\s*["']([a-z][a-z0-9_]{1,24})["']""", window) + re.findall(r"""\[\s*["']([a-z][a-z0-9_]{1,24})["']\s*\]""", window) + re.findall(r"^\s+([a-z][a-z0-9_]{1,24})\s*:\s*(?:str|Optional)", window, re.M)
    keys = list(dict.fromkeys(keys))
    msg = next((k for k in ("message", "text", "prompt", "content", "query", "input", "msg") if k in keys), None)
    img = next((k for k in keys if re.search(r"image|attachment|screenshot|img", k)), None)
    return msg, img, keys[:20]


def at_names():
    src = read(os.path.join(WB, "app_trainee.py"))
    for f in glob.glob(os.path.join(WB, "*.py")):
        if not f.endswith("app_trainee.py"):
            src += read(f)
    names = re.findall(r"""["'\s(]@([a-z][a-z0-9_\-]{1,24})""", src)
    bad = {"app", "property", "staticmethod", "classmethod", "dataclass", "router", "lru_cache", "wraps", "contextmanager", "abstractmethod"}
    return [n for n in dict.fromkeys(names) if n not in bad][:24]


def coding_agents(live_ports):
    pats = ("*agent*.py", "*codefix*.py", "*loucode*.py", "*autocode*.py", "*coder*.py", "*bot*.py", "*swarm*.py")
    found = []
    for base in (HOME, ROOT, os.path.join(HOME, "auto-loucode"), os.path.join(HOME, "loucode"), os.path.join(HOME, "LouBot")):
        for pat in pats:
            for f in glob.glob(os.path.join(base, pat)) + glob.glob(os.path.join(base, "*", pat)):
                src = read(f)
                pm = re.search(r"(?:port\s*=\s*|--port[ =]|PORT\s*=\s*)(\d{4,5})", src)
                port = int(pm.group(1)) if pm else None
                if port in NEVER:
                    port = None
                found.append({"file": f.replace(HOME, "~"), "port": port, "live": bool(port and port in live_ports)})
    seen, out = set(), []
    for a in found:
        if a["file"] not in seen:
            seen.add(a["file"])
            out.append(a)
    return out[:60]


def page_features(port):
    """Read a local web page's own menu: links, tabs and section buttons -> feature tiles."""
    code, html = get("http://127.0.0.1:%d/" % port, 2.5)
    if code != 200 or "<" not in html[:2000]:
        return None, []
    tm = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", tm.group(1))).strip()[:40] if tm else ""
    feats = []
    def clean(t):
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)).replace("&amp;", "&").strip()[:28]
    for m in re.finditer(r"""<a\b[^>]*href=["']([^"']+)["'][^>]*>(.*?)</a>""", html, re.S | re.I):
        href, label = m.group(1).strip(), clean(m.group(2))
        if not label or href.startswith(("http://", "https://", "mailto:", "javascript:", "//")) and "127.0.0.1:%d" % port not in href:
            continue
        if href in ("#", "/") or href.endswith((".css", ".js", ".png", ".ico")):
            continue
        url = href if href.startswith("http") else "http://127.0.0.1:%d%s%s" % (port, "/" if href.startswith("#") else "", href if href.startswith(("/", "#")) else "/" + href)
        feats.append((label, url))
    for m in re.finditer(r"""<(?:button|div|li|span|a)\b[^>]*data-(?:tab|view|panel|route|section|surface|page|target)=["']([^"']+)["'][^>]*>(.*?)</(?:button|div|li|span|a)>""", html, re.S | re.I):
        val, label = m.group(1).strip(), clean(m.group(2))
        if label and not re.search(r"close|cancel|minimi[sz]e|×|✕", label, re.I):
            feats.append((label, "http://127.0.0.1:%d/#%s" % (port, val.lstrip("#"))))
    seen, out = set(), []
    for label, url in feats:
        k = label.lower()
        if k not in seen and len(label) > 1:
            seen.add(k)
            out.append((label, url))
    return title, out[:20]


def main():
    yes = "--yes" in sys.argv
    hub = find_hub(sys.argv[1:])
    cfgp = os.path.join(hub, "modules.json")
    cfg = json.load(open(cfgp))
    print("LOUSTA CONNECT  hub=%s" % hub)
    print("MUTATION=only %s after you confirm   POST=NO   RESTART=NO   11884=NEVER   PRODUCTION=LOCKED\n" % cfgp)

    print("1. SERVICES (GET)")
    ports = dict(KNOWN)
    for p, src in script_ports().items():
        ports.setdefault(p, "from " + src)
    live = {}
    for p in sorted(ports):
        if p in NEVER:
            continue
        code, _ = get("http://127.0.0.1:%d/" % p, 1.5)
        if code is not None:
            live[p] = code
            print("   UP   :%-5d HTTP_%s  %s" % (p, code, ports[p]))
    down = [p for p in KNOWN if p not in live and p not in NEVER]
    print("   DOWN : " + ", ".join(":%d %s" % (p, KNOWN[p]) for p in sorted(down)))

    print("\n2. LIVE TERMUX (11883)")
    rb, info = readback_route()
    print("   route = %s   %s" % (rb or "NOT FOUND", info))

    print("\n3. BLUEBOT CHAT FIELDS (source read)")
    msg, img, keys = chat_fields()
    print("   message_key=%s  image_key=%s  fields seen=%s" % (msg, img, keys))

    print("\n4. @BOTS BLUEBOT KNOWS")
    names = at_names()
    print("   " + (", ".join("@" + n for n in names) or "none found"))

    print("\n5. CODING AGENTS / BOTS ON THIS PHONE")
    agents = coding_agents(live)
    for a in agents:                       # probe ports named inside agent files too
        p = a["port"]
        if p and p not in live and p not in NEVER:
            code, _ = get("http://127.0.0.1:%d/" % p, 1.5)
            if code is not None:
                live[p] = code
                ports.setdefault(p, os.path.basename(a["file"]))
        a["live"] = bool(p and p in live)
    for a in agents:
        print("   %s %-6s %s" % ("LIVE" if a["live"] else "    ", (":%d" % a["port"]) if a["port"] else "", a["file"]))

    # ---- build proposal ----
    new = json.loads(json.dumps(cfg))
    changes = []
    if rb and new.get("termux", {}).get("readback_url") != rb:
        new.setdefault("termux", {})["readback_url"] = rb
        changes.append("termux.readback_url = " + rb)
    if msg and new.get("chat", {}).get("message_key") != msg:
        new.setdefault("chat", {})["message_key"] = msg
        changes.append("chat.message_key = " + msg)
    if img and not new.get("chat", {}).get("image_key"):
        new["chat"]["image_key"] = img
        changes.append("chat.image_key = " + img)
    have = {b.get("prefix", "").strip().lstrip("@") for b in new.get("bots", [])}
    k = 0
    for n in names:
        if n in have:
            continue
        new.setdefault("bots", []).append({"id": re.sub(r"[^a-z0-9_]", "_", n), "label": n.replace("-", " ").replace("_", " ").title(),
                                            "icon": ICONS[k % len(ICONS)], "prefix": "@" + n + " ", "color": PALETTE[k % len(PALETTE)],
                                            "desc": "Found in BlueBot (11880) as @" + n})
        changes.append("bot @" + n)
        k += 1
    hp = {h["port"] for h in new.get("health", [])}
    for p, code in sorted(live.items()):
        if p not in hp and p not in NEVER:
            new["health"].append({"port": p, "role": ports.get(p, "Service"), "url": "http://127.0.0.1:%d/" % p})
            changes.append("health :%d %s" % (p, ports.get(p, "")))
    mids = {m["id"] for m in new["modules"]}
    for a in agents:
        if a["live"]:
            mid = "agent_%d" % a["port"]
            if mid not in mids:
                name = os.path.basename(a["file"]).rsplit(".", 1)[0].replace("_", " ").title()[:22]
                new["modules"].append({"id": mid, "label": name, "icon": "🤖", "category": "Agents", "url": "http://127.0.0.1:%d/" % a["port"]})
                mids.add(mid)
                changes.append("tile Agents/%s :%d" % (name, a["port"]))

    print("\n6. FEATURES INSIDE EACH LOCAL WEB PAGE (menus, tabs, sections)")
    for p in sorted(live):
        if p in NEVER or p in (11437, 11438):
            continue
        title, feats = page_features(p)
        if not feats:
            continue
        cat = "%s (:%d)" % (title or ports.get(p, "Page"), p)
        print("   :%d %s -> %s" % (p, title or "", ", ".join(f[0] for f in feats)))
        urls = {m.get("url") for m in new["modules"]}
        for i, (label, url) in enumerate(feats):
            if url in urls:
                continue
            mid = re.sub(r"[^a-z0-9_]", "_", ("f%d_%s" % (p, label)).lower())[:40]
            if mid in mids:
                continue
            new["modules"].append({"id": mid, "label": label.title() if label.isupper() else label, "icon": "◇", "category": cat, "url": url})
            mids.add(mid)
            urls.add(url)
            changes.append("tile %s / %s" % (cat, label))

    print("\n==================== PROPOSED CONNECTIONS ====================")
    if not changes:
        print("   nothing new to connect (already wired, or services are down - start them, then run again)")
        return 0
    for c in changes:
        print("   + " + c)
    if not yes:
        try:
            ans = input("\nApply these to %s ? [y/N] " % cfgp).strip().lower()
        except EOFError:
            ans = ""
        if ans != "y":
            print("NOT APPLIED. Nothing changed.")
            return 0
    bak = cfgp + ".bak_" + time.strftime("%Y%m%d_%H%M%S")
    shutil.copy2(cfgp, bak)
    with open(cfgp, "w", encoding="utf-8") as f:
        json.dump(new, f, indent=1, ensure_ascii=False)
    print("APPLIED. Backup: %s\nReload 127.0.0.1:11082 (no restart needed).\nROLLBACK: cp '%s' '%s'" % (bak, bak, cfgp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
