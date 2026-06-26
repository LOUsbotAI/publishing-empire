"""
Audiobook pack generator.
Uses OpenAI TTS (or falls back to a placeholder) to produce per-chapter MP3s.
"""
import os
import json
import pathlib
import datetime
from dotenv import load_dotenv

load_dotenv(pathlib.Path.home() / ".lousta_system_core" / "secrets" / ".env")

AUDIO_DIR = pathlib.Path.home() / "lousta-core" / "output" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def _tts_client():
    key = os.getenv("OPENAI_API_KEY", "")
    if not key or len(key) < 20:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=key)
    except ImportError:
        return None


def _chapter_to_mp3(client, text: str, out_path: pathlib.Path) -> bool:
    if client is None:
        out_path.write_bytes(b"")  # placeholder empty file
        return False

    response = client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=text[:4096],  # TTS endpoint limit
    )
    response.stream_to_file(str(out_path))
    return True


def generate_audiobook(book: dict) -> dict:
    """
    Accepts a forge_mint result dict and writes per-chapter MP3s.
    Returns a manifest of output paths.
    """
    client = _tts_client()
    slug = book["title"].lower().replace(" ", "_")
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    book_dir = AUDIO_DIR / f"{slug}_{ts}"
    book_dir.mkdir(parents=True, exist_ok=True)

    tracks = []
    for ch in book["chapters"]:
        out = book_dir / f"chapter_{ch['chapter']:02d}.mp3"
        real = _chapter_to_mp3(client, ch["text"], out)
        tracks.append({
            "chapter": ch["chapter"],
            "path": str(out),
            "real_audio": real,
        })

    manifest = {
        "title": book["title"],
        "author": book["author"],
        "generated": datetime.datetime.now().isoformat(),
        "tracks": tracks,
    }
    (book_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python audiobook.py <forge_mint_result.json>")
        raise SystemExit(1)

    book = json.loads(pathlib.Path(sys.argv[1]).read_text())
    result = generate_audiobook(book)
    print(json.dumps(result, indent=2))
