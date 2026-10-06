#!/usr/bin/env python3
"""Check a team-built hub module before Louie promotes it. Read-only.
Usage: python3 check_module.py path/to/<name>.js
Exit 0 = PASS, 1 = HOLD (reasons printed)."""
import os
import re
import shutil
import subprocess
import sys

FORBIDDEN = [
    (r"\bfetch\s*\(", "direct fetch (use api.get)"),
    (r"XMLHttpRequest|WebSocket|EventSource|sendBeacon", "direct network transport"),
    (r"\beval\s*\(|new\s+Function\s*\(|\bimport\s*\(", "dynamic code"),
    (r"innerHTML\s*=|outerHTML\s*=|insertAdjacentHTML|document\.write", "raw HTML injection (use api.el / textContent)"),
    (r"11884|tmux|/api/tmux|run-approved|stage-approved|release-approved|/loukey/auto|/api/decision|/api/gate", "execution or gate path"),
    (r"['\"](POST|PUT|PATCH|DELETE)['\"]", "write method"),
    (r"document\.cookie|localStorage\.clear|sessionStorage\.clear", "storage tampering"),
    (r"https?://(?!127\.0\.0\.1|localhost)[a-z0-9]", "non-local URL"),
    (r"window\.LoustaHub\s*=|LoustaHub\s*=", "overwrites the hub API"),
]


def main(path):
    reasons = []
    name = os.path.basename(path)
    m = re.match(r"^([a-z0-9_]{1,40})\.js$", name)
    if not m:
        reasons.append("file name must be <lowercase_name>.js")
    src = open(path, encoding="utf-8").read()
    if len(src) > 100_000:
        reasons.append("larger than 100 KB")
    if m and not re.search(r"LoustaHub\.register\(\s*\{[^}]*id:\s*['\"]%s['\"]" % m.group(1), src, re.S):
        reasons.append("must call LoustaHub.register({id:'%s', ...})" % (m.group(1) if m else "?"))
    if "render" not in src:
        reasons.append("missing render(el, api)")
    # blank out /* block comments */ (keep line numbers), then // line comments (not the // in URLs)
    body = re.sub(r"/\*.*?\*/", lambda x: "\n" * x.group(0).count("\n"), src, flags=re.S)
    for i, line in enumerate(body.splitlines(), 1):
        code = re.sub(r"(^|[^:])//.*$", r"\1", line)
        for pat, why in FORBIDDEN:
            if re.search(pat, code):
                reasons.append("line %d: %s" % (i, why))
    node = shutil.which("node")
    if node:
        r = subprocess.run([node, "--check", path], capture_output=True, text=True)
        if r.returncode != 0:
            reasons.append("JS syntax: " + (r.stderr.strip().splitlines() or ["error"])[-1])
    else:
        print("NOTE=node not installed, JS syntax not checked")
    print("MODULE=%s" % name)
    if reasons:
        for x in reasons:
            print("HOLD=" + x)
        return 1
    print("CHECK=PASS")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
