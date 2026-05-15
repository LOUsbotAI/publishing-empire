#!/usr/bin/env python3
"""
Content Validator
=================
Diagnoses the #1 root cause of placeholder books:
  "This is fallback scaffold content... Wire a valid model/API key"

Run this BEFORE generating any books. It verifies:
  1. API keys exist and are valid (live call)
  2. Generated PDFs/manuscripts are real content (not scaffolds)
  3. Audio files are real audio (not 68-104 byte stubs)

Usage (in Termux):
  python3 validate_content.py                   # full check
  python3 validate_content.py --fix             # attempt auto-fix
  python3 validate_content.py --scan ~/lousta-core/output
"""
import json
import os
import sys
from pathlib import Path
import argparse

# ─── SCAFFOLD DETECTION STRINGS ──────────────────────────────────────────────
SCAFFOLD_SIGNATURES = [
    "fallback scaffold content",
    "Wire a valid model/API key to replace this fallback",
    "This is a scaffold chapter",
    "Replace this with your real AI manuscript pipeline",
    "Prompt basis:",                       # raw prompt leaked into content
    "This is fallback",
    "placeholder content",
    "scaffold content",
]

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "

results = []

def check(label, ok, detail=""):
    icon = PASS if ok else FAIL
    results.append({"label": label, "ok": ok, "detail": detail})
    print(f"  {icon} {label}" + (f": {detail}" if detail else ""))
    return ok


# ─── API KEY CHECKS ───────────────────────────────────────────────────────────

def check_anthropic():
    print("\n[1/5] Anthropic Claude API")
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        check("ANTHROPIC_API_KEY", False, "MISSING from .env")
        return False
    if not key.startswith("sk-ant"):
        check("ANTHROPIC_API_KEY format", False, f"looks wrong: {key[:12]}...")
        return False

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": "Say: OK"}],
        )
        text = msg.content[0].text.strip()
        check("Anthropic API live call", True, f"responded: '{text[:20]}'")
        return True
    except Exception as e:
        check("Anthropic API live call", False, str(e)[:80])
        return False


def check_gemini():
    print("\n[2/5] Google Gemini API")
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        check("GEMINI_API_KEY", False, "MISSING from .env")
        return False
    if not key.startswith("AIza"):
        check("GEMINI_API_KEY format", False, f"looks wrong: {key[:12]}...")
        return False

    try:
        import requests
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={key}",
            json={"contents": [{"parts": [{"text": "Say: OK"}]}]},
            timeout=15,
        )
        if r.status_code == 200:
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"][:20]
            check("Gemini API live call", True, f"responded: '{text}'")
            return True
        else:
            error = r.json().get("error", {}).get("message", r.text[:60])
            check("Gemini API live call", False, error)
            return False
    except Exception as e:
        check("Gemini API live call", False, str(e)[:80])
        return False


def check_elevenlabs():
    print("\n[3/5] ElevenLabs TTS API")
    key = os.getenv("ELEVENLABS_API_KEY", "")
    if not key:
        check("ELEVENLABS_API_KEY", False, "MISSING — audio will be silent/stub")
        return False

    try:
        import requests
        r = requests.get(
            "https://api.elevenlabs.io/v1/user",
            headers={"xi-api-key": key},
            timeout=10,
        )
        if r.status_code == 200:
            quota = r.json().get("subscription", {})
            used = quota.get("character_count", 0)
            limit = quota.get("character_limit", 0)
            remaining = limit - used
            check("ElevenLabs API", True, f"{remaining:,} characters remaining")
            if remaining < 10000:
                print(f"  {WARN} Low quota: only {remaining:,} chars left")
            return True
        else:
            check("ElevenLabs API", False, f"HTTP {r.status_code}: {r.text[:60]}")
            return False
    except Exception as e:
        check("ElevenLabs API live call", False, str(e)[:80])
        return False


# ─── CONTENT QUALITY CHECKS ───────────────────────────────────────────────────

def is_scaffold(text: str) -> tuple[bool, str]:
    """Returns (is_scaffold, matched_signature)."""
    text_lower = text.lower()
    for sig in SCAFFOLD_SIGNATURES:
        if sig.lower() in text_lower:
            return True, sig
    return False, ""


def check_manuscripts(scan_dir: Path):
    print(f"\n[4/5] Manuscript content quality ({scan_dir})")
    txt_files = list(scan_dir.rglob("*.txt")) + list(scan_dir.rglob("*.md"))

    if not txt_files:
        print(f"  {WARN} No .txt/.md files found in {scan_dir}")
        return

    scaffold_count = 0
    real_count = 0
    short_count = 0

    for f in txt_files[:50]:  # cap at 50
        try:
            text = f.read_text(errors="ignore")
            word_count = len(text.split())
            scaffold, sig = is_scaffold(text)

            if scaffold:
                scaffold_count += 1
                if scaffold_count <= 3:
                    print(f"  {FAIL} SCAFFOLD: {f.name} — matched: '{sig}'")
            elif word_count < 100:
                short_count += 1
                if short_count <= 3:
                    print(f"  {WARN} TOO SHORT ({word_count} words): {f.name}")
            else:
                real_count += 1
        except Exception:
            pass

    total = len(txt_files)
    check("Manuscripts: real content",
          scaffold_count == 0,
          f"{real_count} real, {scaffold_count} scaffold, {short_count} too-short (of {total})")

    if scaffold_count > 0:
        print(f"\n  ROOT CAUSE: API key not working when content was generated.")
        print(f"  FIX: Validate API keys above, then regenerate these books.")


def check_audio_files(scan_dir: Path):
    print(f"\n[5/5] Audio file quality ({scan_dir})")
    mp3_files = list(scan_dir.rglob("*.mp3"))

    if not mp3_files:
        print(f"  {WARN} No .mp3 files found")
        return

    stub_count = 0
    real_count = 0
    MIN_REAL_SIZE = 50_000  # 50KB minimum for real audio

    for f in mp3_files[:50]:
        size = f.stat().st_size
        if size < MIN_REAL_SIZE:
            stub_count += 1
            if stub_count <= 3:
                print(f"  {FAIL} STUB ({size} bytes): {f.name}")
        else:
            real_count += 1

    total = len(mp3_files)
    check("Audio files: real content",
          stub_count == 0,
          f"{real_count} real (>50KB), {stub_count} stubs (<50KB) of {total} files")

    if stub_count > 0:
        print(f"\n  ROOT CAUSE: ElevenLabs API not connected or quota exhausted.")
        print(f"  FIX: Set valid ELEVENLABS_API_KEY, then regenerate audio.")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Validate content pipeline health")
    parser.add_argument("--scan", default=str(Path.home() / "lousta-core/output"),
                        help="Directory to scan for manuscripts and audio")
    parser.add_argument("--fix", action="store_true",
                        help="Show fix instructions interactively")
    args = parser.parse_args()

    # Load .env files
    for env_path in [
        Path.home() / ".lousta_system_core/secrets/.env",
        Path(".env"),
        Path("../.env"),
    ]:
        if env_path.exists():
            for line in env_path.read_text(errors="ignore").splitlines():
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"\''))
            print(f"Loaded: {env_path}")
            break

    print("\n" + "=" * 60)
    print("  LOUSTA CONTENT VALIDATOR")
    print("  Checking: API keys + manuscript quality + audio quality")
    print("=" * 60)

    anthropic_ok = check_anthropic()
    gemini_ok    = check_gemini()
    elevenlabs_ok = check_elevenlabs()

    scan_path = Path(args.scan).expanduser()
    if scan_path.exists():
        check_manuscripts(scan_path)
        check_audio_files(scan_path)
    else:
        print(f"\n{WARN} Scan directory not found: {scan_path}")

    print("\n" + "=" * 60)
    all_ok = all(r["ok"] for r in results)
    if all_ok:
        print(f"  {PASS} ALL CHECKS PASSED — content pipeline is live")
    else:
        failed = [r for r in results if not r["ok"]]
        print(f"  {FAIL} {len(failed)} issues found. Fix priority:")
        for i, r in enumerate(failed, 1):
            print(f"  {i}. {r['label']}: {r.get('detail', '')}")

        print("""
FIX INSTRUCTIONS:
─────────────────
1. Get a fresh Anthropic API key:
   https://console.anthropic.com/settings/keys
   → In Termux: echo 'ANTHROPIC_API_KEY=sk-ant-...' >> ~/.lousta_system_core/secrets/.env

2. Get a fresh Gemini API key:
   https://aistudio.google.com/apikey
   → In Termux: echo 'GEMINI_API_KEY=AIzaSy...' >> ~/.lousta_system_core/secrets/.env

3. Get an ElevenLabs key (for real audio):
   https://elevenlabs.io → API Keys
   → In Termux: echo 'ELEVENLABS_API_KEY=...' >> ~/.lousta_system_core/secrets/.env

4. Restart production processes:
   pm2 restart all
""")

    print("=" * 60)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
