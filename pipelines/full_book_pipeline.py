"""
Full Book Pipeline
==================
The single entry point for everything.
Call this once — it does research, writes, produces, and launches everywhere.

Usage:
    from pipelines.full_book_pipeline import run
    run(niche="self-help", language="en")
    run(niche="business", language="es")   # Spanish edition
"""
import logging
from pathlib import Path

import config
import database as db
from agents import research_agent, content_agent, production_agent
from pipelines import launch_pipeline

log = logging.getLogger("full_pipeline")


def run(niche: str = None, language: str = None, brief: dict = None,
        content_type: str = "both") -> dict:
    """
    content_type: "ebook" | "audiobook" | "both"
    """
    niche = niche or config.TARGET_NICHES[0]
    language = language or config.PRIMARY_LANGUAGE

    log.info("━" * 60)
    log.info("FULL PIPELINE: niche=%s lang=%s type=%s", niche, language, content_type)
    log.info("━" * 60)

    # ── 1. RESEARCH ───────────────────────────────────────────────────────────
    if brief is None:
        log.info("Step 1/5: Market research...")
        opportunities = research_agent.find_opportunities([niche], language, count=1)
        if not opportunities:
            raise RuntimeError(f"No opportunities found for niche: {niche}")
        brief = research_agent.generate_book_brief(opportunities[0])

    brief["language"] = language
    brief["niche"] = niche
    title = brief["title"]
    log.info("✅ Brief: '%s'", title)

    # ── 2. WRITE ──────────────────────────────────────────────────────────────
    log.info("Step 2/5: Writing manuscript...")
    job_id = db.create_job("full", niche, language, meta=brief)
    db.update_job(job_id, "writing", title=title)

    slug = _slug(title, language)
    work_dir = config.BASE_DIR / "output" / "books" / slug
    work_dir.mkdir(parents=True, exist_ok=True)

    manuscript_path = content_agent.write_full_manuscript(brief, work_dir)
    log.info("✅ Manuscript: %s", manuscript_path.name)

    # ── 3. PRODUCE ────────────────────────────────────────────────────────────
    log.info("Step 3/5: Producing assets...")
    db.update_job(job_id, "producing")

    # Cover art
    cover_path = work_dir / "cover.jpg"
    production_agent.generate_cover(
        brief.get("cover_art_prompt", f"Premium book cover: {title}"),
        cover_path
    )

    # Ebook (EPUB + PDF)
    epub_path = production_agent.manuscript_to_epub(manuscript_path, work_dir, title)
    pdf_path = production_agent.manuscript_to_pdf(manuscript_path, work_dir)

    # Audiobook (if requested)
    audio_dir = None
    if content_type in ("audiobook", "both"):
        log.info("  Producing audiobook...")
        audio_dir = work_dir / "audio"
        try:
            production_agent.manuscript_to_audiobook(manuscript_path, audio_dir, title)
            log.info("  ✅ Audio: %d chapters", len(list(audio_dir.glob("*.mp3"))))
        except Exception as e:
            log.warning("  Audio production failed (ElevenLabs key set?): %s", e)
            audio_dir = None

    # ── 4. SAVE TO DATABASE ───────────────────────────────────────────────────
    price = brief.get("suggested_price_usd", 9.99)
    audio_price = price * 1.5  # Audiobooks priced higher

    ebook_product_id = db.save_product(
        job_id=job_id,
        title=title,
        product_type="ebook",
        language=language,
        file_path=str(epub_path),
        platform="multi",
        price_usd=price,
        meta=brief,
    )

    audio_product_id = None
    if audio_dir:
        audio_product_id = db.save_product(
            job_id=job_id,
            title=f"{title} (Audiobook)",
            product_type="audiobook",
            language=language,
            file_path=str(audio_dir),
            platform="multi",
            price_usd=audio_price,
            meta=brief,
        )

    # ── 5. LAUNCH EVERYWHERE ─────────────────────────────────────────────────
    log.info("Step 4/5: Launching on all platforms...")
    db.update_job(job_id, "launching")

    ebook_results = launch_pipeline.launch_everywhere(
        brief=brief,
        product_id=ebook_product_id,
        manuscript_path=manuscript_path,
        epub_path=epub_path,
        cover_path=cover_path,
    )

    audio_results = {}
    if audio_dir and audio_product_id:
        audio_brief = dict(brief, type="audiobook",
                           suggested_price_usd=audio_price,
                           title=f"{title} (Audiobook)")
        audio_results = launch_pipeline.launch_everywhere(
            brief=audio_brief,
            product_id=audio_product_id,
            manuscript_path=manuscript_path,
            audio_dir=audio_dir,
            cover_path=cover_path,
        )

    # ── 5. VIDEO MARKETING ────────────────────────────────────────────────────
    log.info("Step 5/5: Producing video marketing content...")
    try:
        from pipelines import video_pipeline
        video_pipeline.run_short_form_batch(brief, language, count=5)
        log.info("✅ 5 short-form marketing videos produced")
    except Exception as e:
        log.warning("Short-form video failed: %s", e)

    db.update_job(job_id, "complete")

    summary = {
        "title": title,
        "language": language,
        "niche": niche,
        "ebook": ebook_results,
        "audiobook": audio_results,
        "files": {
            "manuscript": str(manuscript_path),
            "epub": str(epub_path),
            "pdf": str(pdf_path) if pdf_path else None,
            "cover": str(cover_path),
            "audio_dir": str(audio_dir) if audio_dir else None,
        }
    }

    log.info("━" * 60)
    log.info("COMPLETE: '%s' is LIVE on %d platforms", title,
             len(ebook_results.get("live_on", [])) + len(audio_results.get("live_on", [])))
    log.info("━" * 60)
    return summary


def _slug(title: str, lang: str) -> str:
    import re
    s = re.sub(r"[^a-zA-Z0-9]+", "_", title.lower())[:40]
    return f"{s}_{lang}"
