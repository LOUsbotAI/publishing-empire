#!/usr/bin/env python3
"""BlueBot 11082 hub: one screen that brings the separate pages together.

Read-only by design, with one exception:
  - binds 127.0.0.1 only
  - answers GET/HEAD; the ONLY write is POST /hub/chat, which forwards the
    body unchanged to the existing BlueBot chat route (127.0.0.1 .../api/chat).
    That is the same chat behaviour 1182 already has. Every other write -> 405
  - GET /hub/get?u=<127.0.0.1 url> reads (never writes) services listed in
    modules.json "health", never port 11884, for native modules built by the team
  - serves index.html + modules.json, and /hub/health (server-side GET probes
    of 127.0.0.1 URLs listed in modules.json)
  - no proxying of actions, no subprocess, no tmux, no 11884
Pages are shown in iframes straight from their own ports, so each page keeps
its own existing rules and buttons.
"""
import json
import re
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
HOST = "127.0.0.1"
PORT = int(os.environ.get("HUB_PORT", "11082"))
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/index.html": ("index.html", "text/html; charset=utf-8"),
          "/modules.json": ("modules.json", "application/json"),
          "/work_orders.json": ("work_orders.json", "application/json")}
VERSION = "BLUEBOT_HUB_11082_V3"
MAX_CHAT_BYTES = 3 * 1024 * 1024   # room for one compressed screenshot
MAX_READ_BYTES = 2 * 1024 * 1024
NEVER_PORTS = {11884}          # owner-manual input: never readable or reachable through the hub
MODULE_RE = re.compile(r"^/modules/([a-z0-9_]{1,40})\.js$")


def local_only(url):
    p = urlsplit(url)
    return p.scheme == "http" and p.hostname in ("127.0.0.1", "localhost")


def load_config():
    with open(os.path.join(HERE, "modules.json"), encoding="utf-8") as f:
        return json.load(f)


def probe(item):
    url = item.get("url", "")
    out = {"port": item.get("port"), "role": item.get("role"), "url": url}
    if not local_only(url):
        out.update(state="REFUSED_NON_LOCAL", code=None, ms=None)
        return out
    t = time.monotonic()
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": VERSION})
        with urllib.request.urlopen(req, timeout=2) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception:
        code = None
    out["ms"] = round((time.monotonic() - t) * 1000)
    out["code"] = code
    out["state"] = "DOWN" if code is None else ("ERROR" if code == 404 or code >= 500 else "UP")
    return out


class Hub(BaseHTTPRequestHandler):
    server_version = VERSION

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def send_json(self, code, obj):
        self.send(code, json.dumps(obj, separators=(",", ":")).encode(), "application/json")

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in STATIC:
            name, ctype = STATIC[path]
            with open(os.path.join(HERE, name), "rb") as f:
                return self.send(200, f.read(), ctype)
        if path == "/hub/health":
            items = load_config().get("health", [])
            with ThreadPoolExecutor(max_workers=max(1, len(items))) as ex:
                results = list(ex.map(probe, items))
            return self.send_json(200, {"version": VERSION, "ts": int(time.time()),
                                        "production": "LOCKED", "execution": "NONE",
                                        "services": results})
        mm = MODULE_RE.match(path)
        if mm:
            f = os.path.join(HERE, "modules", mm.group(1) + ".js")
            if not os.path.isfile(f):
                return self.send_json(404, {"error": "MODULE_NOT_FOUND"})
            with open(f, "rb") as fh:
                return self.send(200, fh.read(), "text/javascript; charset=utf-8")
        if path == "/hub/get":
            return self.read_proxy()
        if path == "/hub/status":
            return self.send_json(200, {"version": VERSION, "port": PORT, "dir": HERE, "methods": ["GET", "HEAD", "POST /hub/chat only"],
                                        "execution": "NONE", "production": "LOCKED"})
        self.send_json(404, {"error": "NOT_FOUND"})

    do_HEAD = do_GET

    def read_proxy(self):
        """GET-only read of another local service, for native modules (avoids CORS)."""
        q = parse_qs(urlsplit(self.path).query)
        url = (q.get("u") or [""])[0]
        p = urlsplit(url)
        allowed = {int(h.get("port")) for h in load_config().get("health", []) if h.get("port")}
        if not local_only(url) or p.port is None or p.port in NEVER_PORTS or p.port not in allowed:
            return self.send_json(403, {"error": "READ_TARGET_NOT_ALLOWED", "allowed_ports": sorted(allowed - NEVER_PORTS)})
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": VERSION})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                code, data, ctype = r.status, r.read(MAX_READ_BYTES + 1), r.headers.get("Content-Type", "text/plain")
        except urllib.error.HTTPError as e:
            code, data, ctype = e.code, e.read(MAX_READ_BYTES + 1), "application/json"
        except Exception as e:
            return self.send_json(502, {"error": "UPSTREAM_UNREACHABLE", "detail": type(e).__name__})
        if len(data) > MAX_READ_BYTES:
            return self.send_json(413, {"error": "UPSTREAM_TOO_LARGE"})
        ctype = ctype if ctype.split(";")[0].strip() in ("application/json", "text/plain") else "text/plain; charset=utf-8"
        self.send(code, data, ctype)

    def do_POST(self):
        if urlsplit(self.path).path != "/hub/chat":
            return self.refuse()
        url = load_config().get("chat", {}).get("url", "")
        if not local_only(url) or urlsplit(url).path != "/api/chat":
            return self.send_json(403, {"error": "CHAT_TARGET_NOT_ALLOWED"})
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_CHAT_BYTES:
            return self.send_json(413, {"error": "BODY_SIZE", "max": MAX_CHAT_BYTES})
        body = self.rfile.read(n)
        try:
            json.loads(body)
        except ValueError:
            return self.send_json(400, {"error": "BODY_NOT_JSON"})
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": VERSION})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                code, data = r.status, r.read()
        except urllib.error.HTTPError as e:
            code, data = e.code, e.read()
        except Exception as e:
            return self.send_json(502, {"error": "BLUEBOT_UNREACHABLE", "detail": type(e).__name__})
        self.send(code, data, "application/json")

    def refuse(self):
        self.send_json(405, {"error": "READ_ONLY_HUB", "allowed": ["GET", "HEAD"]})

    do_PUT = do_PATCH = do_DELETE = do_OPTIONS = refuse


if __name__ == "__main__":
    srv = ThreadingHTTPServer((HOST, PORT), Hub)
    print("%s listening on http://%s:%d (GET + chat only, production LOCKED)" % (VERSION, HOST, PORT), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
