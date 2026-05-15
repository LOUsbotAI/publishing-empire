"""
Converts manuscripts into production-ready assets:
- Audiobook MP3s via ElevenLabs TTS
- PDF/EPUB ebooks via Pandoc
- Cover art via Gemini Imagen or DALL-E
- Video files via MoviePy
"""
import io
import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

import requests
import config

log = logging.getLogger(__name__)


# ─── AUDIO ───────────────────────────────────────────────────────────────────

def text_to_speech(text: str, output_path: Path, voice_id: str = None) -> Path:
    """Convert text to MP3 using ElevenLabs."""
    if not config.ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY not set")

    vid = voice_id or config.ELEVENLABS_VOICE_ID
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}"
    headers = {
        "xi-api-key": config.ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    # ElevenLabs has a 5000-char limit per request — chunk if needed
    chunks = _split_text(text, max_chars=4800)
    audio_parts = []

    for i, chunk in enumerate(chunks):
        resp = requests.post(url, headers=headers, json={
            "text": chunk,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
        }, timeout=120)
        resp.raise_for_status()
        part_path = output_path.parent / f"_part_{i}.mp3"
        part_path.write_bytes(resp.content)
        audio_parts.append(part_path)

    if len(audio_parts) == 1:
        audio_parts[0].rename(output_path)
    else:
        _concat_mp3s(audio_parts, output_path)
        for p in audio_parts:
            p.unlink(missing_ok=True)

    log.info("Audio written: %s (%.1f MB)", output_path, output_path.stat().st_size / 1e6)
    return output_path


def manuscript_to_audiobook(manuscript_path: Path, output_dir: Path,
                             title: str, voice_id: str = None) -> list[Path]:
    """Split manuscript by chapter and produce one MP3 per chapter."""
    text = manuscript_path.read_text(encoding="utf-8")
    chapters = re.split(r"(?m)^CHAPTER \d+:", text)
    chapters = [c.strip() for c in chapters if len(c.strip()) > 100]

    output_dir.mkdir(parents=True, exist_ok=True)
    mp3_files = []

    for i, chapter_text in enumerate(chapters, 1):
        out = output_dir / f"chapter_{i:02d}.mp3"
        log.info("Generating audio for chapter %d/%d", i, len(chapters))
        text_to_speech(chapter_text, out, voice_id)
        mp3_files.append(out)

    return mp3_files


def _split_text(text: str, max_chars: int = 4800) -> list[str]:
    """Split on sentence boundaries."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) > max_chars:
            if current:
                chunks.append(current.strip())
            current = s
        else:
            current += " " + s
    if current.strip():
        chunks.append(current.strip())
    return chunks or [text[:max_chars]]


def _concat_mp3s(parts: list[Path], output: Path):
    """Concatenate MP3 files using ffmpeg if available, else raw bytes."""
    try:
        file_list = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        for p in parts:
            file_list.write(f"file '{p.absolute()}'\n")
        file_list.close()
        subprocess.run(
            ["ffmpeg", "-f", "concat", "-safe", "0", "-i", file_list.name,
             "-c", "copy", str(output), "-y"],
            check=True, capture_output=True
        )
        os.unlink(file_list.name)
    except (FileNotFoundError, subprocess.CalledProcessError):
        # Fallback: raw concatenation (works for CBR MP3)
        with open(output, "wb") as out:
            for p in parts:
                out.write(p.read_bytes())


# ─── EBOOK ───────────────────────────────────────────────────────────────────

def manuscript_to_epub(manuscript_path: Path, output_dir: Path,
                        title: str, author: str = "Publishing Empire") -> Path:
    """Convert manuscript to EPUB using Pandoc."""
    out = output_dir / (manuscript_path.stem + ".epub")
    try:
        subprocess.run(
            ["pandoc", str(manuscript_path), "-o", str(out),
             f"--metadata=title:{title}", f"--metadata=author:{author}",
             "--epub-cover-image=" + str(output_dir / "cover.jpg")
             if (output_dir / "cover.jpg").exists() else "",
             ],
            check=True, capture_output=True
        )
    except FileNotFoundError:
        # Pandoc not available — produce basic HTML ebook
        html = f"<html><body><pre>{manuscript_path.read_text()}</pre></body></html>"
        out = output_dir / (manuscript_path.stem + ".html")
        out.write_text(html, encoding="utf-8")
    log.info("Ebook produced: %s", out)
    return out


def manuscript_to_pdf(manuscript_path: Path, output_dir: Path) -> Path:
    """Convert to PDF using Pandoc → WeasyPrint fallback."""
    out = output_dir / (manuscript_path.stem + ".pdf")
    try:
        subprocess.run(
            ["pandoc", str(manuscript_path), "-o", str(out), "--pdf-engine=weasyprint"],
            check=True, capture_output=True
        )
        log.info("PDF produced: %s", out)
    except Exception as e:
        log.warning("PDF conversion failed (%s), skipping", e)
        return None
    return out


# ─── COVER ART ───────────────────────────────────────────────────────────────

def generate_cover(prompt: str, output_path: Path) -> Path:
    """Generate a book cover using Gemini Imagen or fallback to placeholder."""
    if config.GEMINI_API_KEY:
        return _cover_gemini(prompt, output_path)
    log.warning("No image generation API key configured — using placeholder cover")
    return _placeholder_cover(output_path)


def _cover_gemini(prompt: str, output_path: Path) -> Path:
    import google.generativeai as genai  # type: ignore
    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.ImageGenerationModel("imagen-3.0-generate-002")
    result = model.generate_images(
        prompt=f"Book cover design. {prompt}. Professional, high-quality, photorealistic.",
        number_of_images=1,
        aspect_ratio="2:3",
    )
    result.images[0].save(str(output_path))
    log.info("Cover generated: %s", output_path)
    return output_path


def _placeholder_cover(output_path: Path) -> Path:
    """Write a minimal valid JPEG as placeholder."""
    # 1x1 white JPEG
    placeholder = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
        0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
        0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
        0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
        0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
        0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
        0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
        0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
        0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
        0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
        0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
        0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
        0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
        0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
        0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
        0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
        0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD9
    ])
    output_path.write_bytes(placeholder)
    return output_path
