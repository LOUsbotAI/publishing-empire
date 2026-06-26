"""
Forge Mint — AI content generator.
Reads prompts from a manifest, calls OpenAI to produce chapter text,
and falls back to scaffold content when no key is present.
"""
import os
import json
import pathlib
import datetime
from dotenv import load_dotenv

load_dotenv(pathlib.Path.home() / ".lousta_system_core" / "secrets" / ".env")

EXPORT_DIR = pathlib.Path.home() / "lousta-core" / "output" / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

FALLBACK_TEMPLATE = (
    "This is fallback scaffold content for {title}. "
    "Wire a valid model/API key to replace this fallback."
)


def _openai_client():
    key = os.getenv("OPENAI_API_KEY", "")
    if not key or len(key) < 20:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=key)
    except ImportError:
        return None


def generate_chapter(title: str, prompt: str, chapter_num: int) -> str:
    client = _openai_client()
    if client is None:
        return FALLBACK_TEMPLATE.format(title=title)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a professional non-fiction author writing practical, "
                    "sellable guides. Write in clear, actionable prose."
                ),
            },
            {
                "role": "user",
                "content": f"Write Chapter {chapter_num} of '{title}'.\n\nPrompt: {prompt}",
            },
        ],
        max_tokens=1200,
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


def forge_book(manifest: dict) -> dict:
    """
    manifest = {
        "title": str,
        "author": str,
        "chapters": [{"prompt": str}, ...]
    }
    Returns a result dict with generated chapter texts.
    """
    title = manifest["title"]
    author = manifest.get("author", "Louie")
    chapters = manifest["chapters"]

    result_chapters = []
    for i, ch in enumerate(chapters, start=1):
        prompt = ch.get("prompt", f"Write chapter {i} of {title}.")
        text = generate_chapter(title, prompt, i)
        result_chapters.append({"chapter": i, "prompt": prompt, "text": text})

    result = {
        "title": title,
        "author": author,
        "generated": datetime.datetime.now().isoformat(),
        "chapters": result_chapters,
    }

    slug = title.lower().replace(" ", "_")
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = EXPORT_DIR / f"{slug}_{ts}.json"
    out_path.write_text(json.dumps(result, indent=2))

    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        # Run the same manifest as the Forge Mint test
        manifest = {
            "title": "Forge Mint Test",
            "author": "Louie",
            "chapters": [
                {"prompt": "Create a practical sellable guide about Termux AI publishing systems."}
                for _ in range(7)
            ],
        }
    else:
        manifest = json.loads(pathlib.Path(sys.argv[1]).read_text())

    out = forge_book(manifest)
    print(f"Generated: {out['title']} — {len(out['chapters'])} chapters")
    for ch in out["chapters"]:
        print(f"\n--- Chapter {ch['chapter']} ---")
        print(ch["text"][:300], "..." if len(ch["text"]) > 300 else "")
