#!/usr/bin/env python3
"""
Key audit — checks which secrets are present in the vault .env.
Prints only masked values; never logs full keys.
"""
import os
import re
import json
import pathlib
import datetime

SECRETS = pathlib.Path.home() / ".lousta_system_core" / "secrets" / ".env"
REPORT_DIR = pathlib.Path(__file__).parent.parent / "reports"
REPORT_DIR.mkdir(exist_ok=True)

WANTED = [
    "OPENAI_API_KEY",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_PUBLIC_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "CLOUDFLARE_API_TOKEN",
    "TTS_PROVIDER_KEY",
]


def mask(val: str) -> str:
    if len(val) >= 14:
        return val[:8] + "****" + val[-4:]
    if val:
        return val[:4] + "****"
    return "MISSING"


def audit() -> list:
    text = SECRETS.read_text(errors="ignore") if SECRETS.exists() else ""
    report = []
    for key in WANTED:
        m = re.search(r"^" + re.escape(key) + r"=(.+)$", text, re.M)
        val = m.group(1).strip().strip("\"'") if m else ""
        report.append(
            {
                "key": key,
                "status": "FOUND_MASKED" if val else "MISSING",
                "masked": mask(val),
                "length": len(val),
            }
        )
    return report


if __name__ == "__main__":
    result = audit()
    out = {
        "generated": datetime.datetime.now().isoformat(),
        "secrets_path": str(SECRETS),
        "secrets_file_exists": SECRETS.exists(),
        "keys": result,
    }
    report_path = REPORT_DIR / "active_key_audit.json"
    report_path.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    missing = [r["key"] for r in result if r["status"] == "MISSING"]
    if missing:
        print(f"\n⚠️  Missing keys: {', '.join(missing)}")
        print(f"   Add them to: {SECRETS}")
    else:
        print("\n✅ All keys present")
