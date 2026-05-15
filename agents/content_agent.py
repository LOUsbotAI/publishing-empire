"""
Writes full book manuscripts and video scripts using Claude.
Supports multi-language output for international distribution.
"""
import json
import logging
import re
from pathlib import Path
import anthropic
import config

log = logging.getLogger(__name__)
_client = None

# Scaffold signatures — any chapter containing these is a generation failure
_SCAFFOLD_SIGS = [
    "fallback scaffold content",
    "wire a valid model/api key",
    "this is a scaffold chapter",
    "replace this with your real ai manuscript pipeline",
    "[industrial expert name]",
    "[insert date]",
    "[insert author]",
    "placeholder content",
]

AUTHOR_NAME = "Lousta Corp"  # overridden by brief["author"] if set

def _fill_placeholders(text: str, brief: dict) -> str:
    """Replace any unfilled template placeholders with real values."""
    author = brief.get("author", AUTHOR_NAME)
    title  = brief.get("title", "")
    today  = __import__("datetime").date.today().strftime("%B %Y")
    replacements = {
        "[industrial expert name]": author,
        "[insert author name]": author,
        "[insert author]": author,
        "[author name]": author,
        "[insert date]": today,
        "[insert publication date]": today,
        "[publication date]": today,
        "[insert title]": title,
        "[title]": title,
    }
    for placeholder, value in replacements.items():
        text = re.sub(re.escape(placeholder), value, text, flags=re.IGNORECASE)
    return text

def _is_scaffold(text: str) -> bool:
    low = text.lower()
    return any(sig in low for sig in _SCAFFOLD_SIGS)


def _ai():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


LANG_NAMES = {
    "en": "English", "es": "Spanish", "pt": "Portuguese (Brazilian)",
    "de": "German", "fr": "French", "it": "Italian", "ja": "Japanese",
    "zh": "Simplified Chinese", "ko": "Korean", "ar": "Arabic",
}


def write_chapter(brief: dict, chapter: dict, chapter_num: int) -> str:
    lang = LANG_NAMES.get(brief.get("language", "en"), "English")
    prompt = f"""
You are a professional author writing in {lang}.

Book: "{brief['title']}: {brief.get('subtitle', '')}"
Tone: {brief.get('tone', 'engaging and practical')}
Target audience: {brief.get('audience', 'general readers')}

Write Chapter {chapter_num}: "{chapter['title']}"
Chapter summary: {chapter.get('summary', '')}

Guidelines:
- Write in {lang}, fluently and naturally (not translated-sounding)
- 3,000-4,500 words
- Use subheadings, practical examples, stories
- End with a brief transition to the next chapter
- No meta-commentary, just the chapter content

Write the complete chapter now:
"""
    msg = _ai().messages.create(
        model="claude-opus-4-7",
        max_tokens=6000,
        messages=[{"role": "user", "content": prompt}]
    )
    text = msg.content[0].text.strip()
    text = _fill_placeholders(text, brief)

    if _is_scaffold(text):
        raise RuntimeError(
            f"Chapter {chapter_num} returned scaffold/placeholder text — "
            "API key may be invalid. Run: python3 scripts/validate_content.py"
        )

    min_words = 500
    word_count = len(text.split())
    if word_count < min_words:
        log.warning("Chapter %d is very short (%d words) — may be truncated",
                    chapter_num, word_count)

    return text


def write_full_manuscript(brief: dict, output_dir: Path) -> Path:
    """Write all chapters and assemble into a single manuscript file."""
    title_slug = brief["title"].lower().replace(" ", "_")[:40]
    lang = brief.get("language", "en")
    out_path = output_dir / f"{title_slug}_{lang}.txt"

    chapters = brief.get("chapters", [])
    log.info("Writing %d chapters for '%s' in %s", len(chapters), brief["title"], lang)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"{brief['title']}\n")
        if brief.get("subtitle"):
            f.write(f"{brief['subtitle']}\n")
        f.write("\n\n")
        f.write(f"{brief.get('back_cover_blurb', '')}\n\n")
        f.write("─" * 60 + "\n\n")

        for i, chapter in enumerate(chapters, 1):
            log.info("Writing chapter %d/%d: %s", i, len(chapters), chapter["title"])
            text = write_chapter(brief, chapter, i)
            f.write(f"CHAPTER {i}: {chapter['title'].upper()}\n\n")
            f.write(text)
            f.write("\n\n" + "─" * 60 + "\n\n")

    # Final quality gate — reject entire manuscript if scaffold detected
    final_text = out_path.read_text(encoding="utf-8")
    if _is_scaffold(final_text):
        out_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Manuscript for '{brief['title']}' contains scaffold text — "
            "blocked from production. Check ANTHROPIC_API_KEY validity."
        )

    word_count = len(final_text.split())
    log.info("Manuscript written: %s (%d words)", out_path.name, word_count)

    if word_count < 3000:
        log.warning("Manuscript is short (%d words) — minimum recommended: 5,000+", word_count)

    return out_path


def write_video_script(brief: dict, duration_minutes: int = 10) -> str:
    """Write a YouTube video script from a book brief."""
    lang = LANG_NAMES.get(brief.get("language", "en"), "English")
    prompt = f"""
You are a YouTube scriptwriter creating content in {lang}.

Book/Topic: "{brief['title']}: {brief.get('subtitle', '')}"
Audience: {brief.get('audience', 'general viewers')}
Video length: ~{duration_minutes} minutes (approx {duration_minutes * 130} words spoken)

Write a complete YouTube video script in {lang} including:
- Hook (first 30 seconds — pattern interrupt)
- Introduction with credibility
- Main content sections with clear transitions
- Call to action (subscribe + get the book/audiobook)

Format with [SECTION NAME] headers and [VISUAL: description] cues.
Write the complete script now:
"""
    msg = _ai().messages.create(
        model="claude-opus-4-7",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text.strip()


def write_short_form_scripts(brief: dict, count: int = 5) -> list[str]:
    """Write TikTok/Reels/Shorts scripts for marketing."""
    lang = LANG_NAMES.get(brief.get("language", "en"), "English")
    prompt = f"""
Write {count} short-form video scripts in {lang} (TikTok/Instagram Reels/YouTube Shorts).
Each script is 45-60 seconds (100-130 words spoken).

Topic: "{brief['title']}" — {brief.get('back_cover_blurb', '')}

Each script should:
- Start with a strong hook (question or bold claim)
- Deliver one powerful insight from the book
- End with a CTA to get the full book/audiobook

Return as JSON array of strings (each string is one script).
Return ONLY valid JSON, no markdown.
"""
    msg = _ai().messages.create(
        model="claude-opus-4-7",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)
