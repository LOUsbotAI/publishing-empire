"""BlueBot multi-brain router for the 11082 hub.

BlueBot (11880) answers first. If it times out, errors or returns nothing, the hub tries the next
brain in modules.json "brains.order": local models first (Qwen 11437, llama 11438), then any remote
provider that has a key in ~/.lousta/keys.env (never committed, never sent to the browser, never logged).
Every reply says which brain answered. Chat only: no tools, no execution, production stays locked.
"""
import json
import os
import time
import urllib.error
import urllib.request

KEYS_FILE = os.path.expanduser(os.environ.get("LOUSTA_KEYS", "~/.lousta/keys.env"))
SYSTEM = ("You are a backup brain for BlueBot, the manager of Louie's Lousta system (Termux on Android). "
          "BlueBot's main pipeline did not answer, so you are answering directly. Be helpful and concise. "
          "You cannot run commands, approve gates or publish anything; production is locked and Louie approves every live action. "
          "When you give a Termux script, give one bash block that is safe to paste.")


def load_keys():
    keys = {}
    try:
        st = os.stat(KEYS_FILE)
        insecure = bool(st.st_mode & 0o077)
        with open(KEYS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                if v:
                    keys[k.strip()] = v
        keys["__insecure__"] = "1" if insecure else ""
    except FileNotFoundError:
        pass
    return keys


def _post(url, body, headers, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8", "replace") or "{}")


def _msgs(text, history):
    out = []
    for h in (history or [])[-10:]:
        role = "assistant" if h.get("role") == "bot" else "user"
        t = str(h.get("text", ""))[:4000]
        if t:
            if out and out[-1]["role"] == role:
                out[-1]["content"] += "\n\n" + t
            else:
                out.append({"role": role, "content": t})
    if out and out[-1]["role"] == "user":
        out[-1]["content"] += "\n\n" + text
    else:
        out.append({"role": "user", "content": text})
    if out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": "(conversation continues)"})
    return out


def _auto_model(base, timeout=4):
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/models", timeout=timeout) as r:
            d = json.loads(r.read().decode())
        return ((d.get("data") or [{}])[0] or {}).get("id") or "local"
    except Exception:
        return "local"


def call_brain(b, keys, text, history, image):
    """Returns reply text or raises. b = brain config dict."""
    t = b.get("type")
    timeout = float(b.get("timeout", 60))
    key = keys.get(b.get("key_env", ""), "") if b.get("key_env") else ""
    model = keys.get(b.get("model_env", ""), "") or b.get("model", "")
    if b.get("key_env") and not key:
        raise LookupError("no key")
    msgs = _msgs(text, history)
    if t == "anthropic":
        if image and image.startswith("data:image/"):
            mt, data = image[5:].split(";base64,", 1)
            msgs[-1]["content"] = [{"type": "image", "source": {"type": "base64", "media_type": mt, "data": data}},
                                   {"type": "text", "text": msgs[-1]["content"]}]
        code, d = _post("https://api.anthropic.com/v1/messages",
                        {"model": model or "claude-opus-5-5", "max_tokens": int(b.get("max_tokens", 16000)),
                         "system": SYSTEM, "messages": msgs},
                        {"x-api-key": key, "anthropic-version": "2023-06-01"}, timeout)
        if d.get("stop_reason") == "refusal":
            raise RuntimeError("refused")
        return "".join(c.get("text", "") for c in d.get("content", []) if c.get("type") == "text").strip()
    if t == "openai":
        base = b["base"]
        if not model:
            if b.get("local"):
                model = _auto_model(base)
            else:
                raise LookupError("no model set (add %s to keys.env)" % b.get("model_env", "MODEL"))
        if image and image.startswith("data:image/"):
            msgs[-1]["content"] = [{"type": "text", "text": msgs[-1]["content"]}, {"type": "image_url", "image_url": {"url": image}}]
        hdr = {"Authorization": "Bearer " + key} if key else {}
        code, d = _post(base.rstrip("/") + "/chat/completions",
                        {"model": model, "messages": [{"role": "system", "content": SYSTEM}] + msgs,
                         "max_tokens": int(b.get("max_tokens", 4096)), "temperature": 0.4}, hdr, timeout)
        ch = (d.get("choices") or [{}])[0].get("message", {})
        c = ch.get("content")
        if isinstance(c, list):
            c = "".join(x.get("text", "") for x in c if isinstance(x, dict))
        return (c or "").strip()
    raise ValueError("unknown brain type %s" % t)


def status(cfg):
    keys = load_keys()
    out = []
    for bid in cfg.get("brains", {}).get("order", []):
        b = cfg["brains"]["list"].get(bid, {})
        has_key = (not b.get("key_env")) or bool(keys.get(b["key_env"]))
        out.append({"id": bid, "label": b.get("label", bid), "local": bool(b.get("local")) or b.get("type") == "bluebot",
                    "ready": has_key, "needs": "" if has_key else b.get("key_env", ""),
                    "model": keys.get(b.get("model_env", ""), "") or b.get("model", "") or ("auto" if b.get("local") else "")})
    return {"keys_file": KEYS_FILE, "keys_file_exists": os.path.exists(KEYS_FILE),
            "keys_file_private": os.path.exists(KEYS_FILE) and not load_keys().get("__insecure__"), "brains": out}


def fallback(cfg, text, history, image, start_after=None, only=None):
    """Try brains in order. Returns (reply, brain_id, tried list)."""
    keys = load_keys()
    order = list(cfg.get("brains", {}).get("order", []))
    if only:
        order = [only] + [x for x in order if x != only]
    tried = []
    for bid in order:
        if bid == "bluebot":
            continue
        b = cfg["brains"]["list"].get(bid)
        if not b or b.get("enabled") is False:
            continue
        t0 = time.monotonic()
        try:
            reply = call_brain(b, keys, text, history, image)
            if reply:
                tried.append({"id": bid, "result": "ok", "ms": round((time.monotonic() - t0) * 1000)})
                return reply, bid, tried
            tried.append({"id": bid, "result": "empty"})
        except LookupError as e:
            tried.append({"id": bid, "result": "skipped: " + str(e)})
        except urllib.error.HTTPError as e:
            tried.append({"id": bid, "result": "HTTP %d" % e.code})
        except Exception as e:
            tried.append({"id": bid, "result": type(e).__name__})
    return None, None, tried
