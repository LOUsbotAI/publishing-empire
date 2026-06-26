"""
Full publish pipeline: Forge Mint → PDF/EPUB → Audiobook.
Usage: python run_pipeline.py [manifest.json]
"""
import sys
import json
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from forge_mint.generator import forge_book
from generator.pdf_epub import generate_pack
from generator.audiobook import generate_audiobook


DEFAULT_MANIFEST = {
    "title": "Forge Mint Test",
    "author": "Louie",
    "chapters": [
        {"prompt": "Create a practical sellable guide about Termux AI publishing systems."}
        for _ in range(7)
    ],
}


def run(manifest: dict) -> dict:
    print(f"[1/3] Generating content: {manifest['title']}")
    book = forge_book(manifest)
    real = all("fallback" not in ch["text"] for ch in book["chapters"])
    print(f"      {'Real AI content' if real else 'Fallback scaffold'} — {len(book['chapters'])} chapters")

    print("[2/3] Building PDF + EPUB pack")
    pack = generate_pack(book)
    print(f"      PDF  → {pack['pdf']}")
    print(f"      EPUB → {pack['epub']}")

    print("[3/3] Generating audiobook")
    audio = generate_audiobook(book)
    real_audio = sum(1 for t in audio["tracks"] if t["real_audio"])
    print(f"      {real_audio}/{len(audio['tracks'])} tracks with real TTS audio")

    return {"book": book, "pack": pack, "audio": audio}


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        manifest = json.loads(pathlib.Path(sys.argv[1]).read_text())
    else:
        manifest = DEFAULT_MANIFEST

    result = run(manifest)
    print("\nDone. Outputs:")
    print(f"  PDF:  {result['pack']['pdf']}")
    print(f"  EPUB: {result['pack']['epub']}")
    print(f"  Audio dir: {result['audio']['tracks'][0]['path'] if result['audio']['tracks'] else 'n/a'}")
