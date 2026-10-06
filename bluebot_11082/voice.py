"""Speech-to-text for the 11082 hub, so voice works in ANY browser (Edge, Samsung, Firefox...).

The browser records audio (MediaRecorder) and POSTs it to /hub/transcribe. This module turns it into text:
  1. local  : whisper.cpp on the phone (private, free) if the binary + model are present
  2. groq   : Groq speech-to-text API      (needs GROQ_API_KEY in ~/.lousta/keys.env)
  3. openai : OpenAI speech-to-text API    (needs OPENAI_API_KEY)
Returns text only. It runs nothing but ffmpeg/whisper with fixed arguments (no shell), and stores nothing.
"""
import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import uuid

import brains


def _expand(p):
    return os.path.expanduser(p or "")


def _local_ready(v):
    loc = v.get("local", {})
    ff = shutil.which(loc.get("ffmpeg", "ffmpeg"))
    wb = next((shutil.which(b) for b in (loc.get("whisper"), "whisper-cli", "whisper-cpp", "whisper") if b and shutil.which(b)), None)
    model = _expand(loc.get("model", "~/.lousta/whisper/ggml-base.bin"))
    return ff, wb, model if os.path.isfile(model) else None


def status(cfg):
    v = cfg.get("voice", {})
    keys = brains.load_keys()
    ff, wb, model = _local_ready(v)
    out = []
    for name in v.get("order", ["local", "groq", "openai"]):
        if name == "local":
            ok = bool(ff and wb and model)
            need = "" if ok else "needs " + ", ".join(x for x, have in (("ffmpeg", ff), ("whisper.cpp", wb), ("model file", model)) if not have)
        else:
            k = {"groq": "GROQ_API_KEY", "openai": "OPENAI_API_KEY"}[name]
            ok, need = bool(keys.get(k)), ("" if keys.get(k) else "needs " + k)
        out.append({"id": name, "ready": ok, "needs": need})
    return {"stt": out}


def _multipart(fields, fname, data, ctype):
    b = "----lousta" + uuid.uuid4().hex
    parts = []
    for k, val in fields.items():
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (b, k, val)).encode())
    parts.append(("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n" % (b, fname, ctype)).encode())
    parts.append(data)
    parts.append(("\r\n--%s--\r\n" % b).encode())
    return b"".join(parts), "multipart/form-data; boundary=" + b


def _remote(url, key, model, audio, ctype, lang):
    ext = "webm" if "webm" in ctype else ("ogg" if "ogg" in ctype else ("mp4" if "mp4" in ctype or "m4a" in ctype else "wav"))
    fields = {"model": model, "response_format": "json"}
    if lang:
        fields["language"] = lang
    body, ct = _multipart(fields, "speech." + ext, audio, ctype or "audio/webm")
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": ct, "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=60) as r:
        return (json.loads(r.read().decode("utf-8", "replace")).get("text") or "").strip()


def _local(v, audio):
    ff, wb, model = _local_ready(v)
    if not (ff and wb and model):
        raise LookupError("local whisper not installed")
    with tempfile.TemporaryDirectory() as d:
        src, wav = os.path.join(d, "in.audio"), os.path.join(d, "in.wav")
        with open(src, "wb") as f:
            f.write(audio)
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", src, "-ar", "16000", "-ac", "1", wav], check=True, timeout=60)
        r = subprocess.run([wb, "-m", model, "-f", wav, "-nt", "-np", "-l", (v.get("lang") or "auto")[:2] or "auto"],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError("whisper failed")
        return " ".join(line.strip() for line in r.stdout.splitlines() if line.strip()).strip()


def transcribe(cfg, audio, ctype):
    v = cfg.get("voice", {})
    keys = brains.load_keys()
    lang = v.get("lang", "")
    tried = []
    for name in v.get("order", ["local", "groq", "openai"]):
        try:
            if name == "local":
                text = _local(v, audio)
            elif name == "groq":
                if not keys.get("GROQ_API_KEY"):
                    raise LookupError("no key")
                text = _remote("https://api.groq.com/openai/v1/audio/transcriptions", keys["GROQ_API_KEY"],
                               keys.get("GROQ_STT_MODEL") or "whisper-large-v3-turbo", audio, ctype, lang)
            elif name == "openai":
                if not keys.get("OPENAI_API_KEY"):
                    raise LookupError("no key")
                text = _remote("https://api.openai.com/v1/audio/transcriptions", keys["OPENAI_API_KEY"],
                               keys.get("OPENAI_STT_MODEL") or "whisper-1", audio, ctype, lang)
            else:
                continue
            tried.append({"id": name, "result": "ok"})
            return text, name, tried
        except LookupError as e:
            tried.append({"id": name, "result": "skipped: " + str(e)})
        except urllib.error.HTTPError as e:
            tried.append({"id": name, "result": "HTTP %d" % e.code})
        except Exception as e:
            tried.append({"id": name, "result": type(e).__name__})
    return None, None, tried
