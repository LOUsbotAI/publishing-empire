"""
Autonomous video pipeline:
Brief → Script → TTS narration → Assemble video → Upload YouTube → Market
"""
import logging
import subprocess
import tempfile
from pathlib import Path

import config
import database as db
from agents import content_agent, production_agent, distribution_agent, marketing_agent

log = logging.getLogger(__name__)


def run_long_form(brief: dict, language: str = None) -> dict:
    """Produce a full YouTube video (10-20 min) from a book brief."""
    language = language or brief.get("language", config.PRIMARY_LANGUAGE)
    title = brief["title"]
    job_id = db.create_job("video_long", brief.get("niche", ""), language)

    try:
        db.update_job(job_id, "scripting", title=title)
        script = content_agent.write_video_script(brief, duration_minutes=12)

        video_dir = config.VIDEOS_DIR / _slug(title, language, "long")
        video_dir.mkdir(parents=True, exist_ok=True)

        # TTS narration
        db.update_job(job_id, "producing")
        narration_path = video_dir / "narration.mp3"
        production_agent.text_to_speech(script, narration_path)

        # Assemble video (narration + black background with title text overlay)
        video_path = _assemble_simple_video(
            narration_path, title, video_dir / "video.mp4"
        )

        # Thumbnail (use book cover or generate)
        thumbnail_path = video_dir / "thumbnail.jpg"
        production_agent.generate_cover(
            f"YouTube thumbnail for: {title}. Eye-catching, bold text, high contrast.",
            thumbnail_path
        )

        product_id = db.save_product(
            job_id=job_id,
            title=title,
            product_type="video_long",
            language=language,
            file_path=str(video_path),
            platform="youtube",
            price_usd=0,
            meta=brief,
        )

        db.update_job(job_id, "distributing")
        product_url = ""
        try:
            product_url = distribution_agent.distribute_product(
                product_id=product_id,
                platform="youtube",
                product_meta=brief,
                file_path=video_path,
                cover_path=thumbnail_path,
            )
        except Exception as e:
            log.warning("YouTube upload failed: %s", e)

        db.update_job(job_id, "complete")
        return {"job_id": job_id, "product_id": product_id,
                "video_path": str(video_path), "url": product_url}

    except Exception as e:
        db.update_job(job_id, "failed")
        log.exception("Video pipeline failed: %s", e)
        raise


def run_short_form_batch(brief: dict, language: str = None, count: int = 5) -> list[dict]:
    """Produce a batch of TikTok/Reels/Shorts from a book brief."""
    language = language or brief.get("language", config.PRIMARY_LANGUAGE)
    scripts = content_agent.write_short_form_scripts(brief, count=count)
    results = []

    shorts_dir = config.VIDEOS_DIR / _slug(brief["title"], language, "shorts")
    shorts_dir.mkdir(parents=True, exist_ok=True)

    for i, script in enumerate(scripts):
        job_id = db.create_job("video_short", brief.get("niche", ""), language)
        try:
            narration_path = shorts_dir / f"short_{i+1}_narration.mp3"
            production_agent.text_to_speech(script, narration_path)
            video_path = _assemble_simple_video(
                narration_path, brief["title"], shorts_dir / f"short_{i+1}.mp4",
                vertical=True
            )
            results.append({"script": script[:100], "video": str(video_path)})
            db.update_job(job_id, "complete", title=f"Short {i+1}: {brief['title'][:30]}")
        except Exception as e:
            log.warning("Short %d failed: %s", i + 1, e)
            db.update_job(job_id, "failed")

    return results


def _assemble_simple_video(narration_path: Path, title: str, output_path: Path,
                            vertical: bool = False) -> Path:
    """
    Assemble a video: audio + generated visuals using ffmpeg.
    Creates a simple colored background with title text overlay.
    Falls back to audio-only MP4 if ffmpeg is unavailable.
    """
    resolution = "1080x1920" if vertical else "1920x1080"
    font_size = 60 if vertical else 80

    try:
        subprocess.run([
            "ffmpeg",
            "-i", str(narration_path),
            "-f", "lavfi",
            "-i", f"color=c=0x1a1a2e:s={resolution}:r=30",
            "-vf", (
                f"drawtext=text='{title[:50].replace(':', '')}'"
                f":fontcolor=white:fontsize={font_size}"
                f":x=(w-text_w)/2:y=(h-text_h)/2"
                f":box=1:boxcolor=black@0.5:boxborderw=10"
            ),
            "-shortest",
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac",
            str(output_path), "-y",
        ], check=True, capture_output=True)
        log.info("Video assembled: %s", output_path)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        # ffmpeg not available — wrap audio as MP4
        log.warning("ffmpeg unavailable (%s) — producing audio-only MP4", e)
        try:
            subprocess.run([
                "ffmpeg", "-i", str(narration_path),
                "-vn", "-acodec", "copy", str(output_path), "-y"
            ], check=True, capture_output=True)
        except Exception:
            # Last resort: just copy the mp3
            import shutil
            output_path = output_path.with_suffix(".mp3")
            shutil.copy(narration_path, output_path)

    return output_path


def _slug(title: str, lang: str, suffix: str = "") -> str:
    import re
    s = re.sub(r"[^a-zA-Z0-9]+", "_", title.lower())[:35]
    return f"{s}_{lang}_{suffix}" if suffix else f"{s}_{lang}"
