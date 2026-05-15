"""
Full autonomous audiobook pipeline:
Research → Write → Produce Audio → Generate Cover → Distribute → Market
"""
import logging
from pathlib import Path

import config
import database as db
from agents import research_agent, content_agent, production_agent, distribution_agent, marketing_agent

log = logging.getLogger(__name__)


def run(niche: str = None, language: str = None, brief: dict = None) -> dict:
    """
    Run the complete audiobook pipeline for one title.
    Pass an existing `brief` to skip research, or provide niche+language to auto-research.
    """
    niche = niche or config.TARGET_NICHES[0]
    language = language or config.PRIMARY_LANGUAGE

    job_id = db.create_job("audiobook", niche, language)
    log.info("Audiobook job %d started — niche: %s, lang: %s", job_id, niche, language)

    try:
        # ── 1. RESEARCH ───────────────────────────────────────────────────────
        if brief is None:
            db.update_job(job_id, "researching")
            opportunities = research_agent.find_opportunities([niche], language, count=1)
            if not opportunities:
                raise RuntimeError("No opportunities found")
            brief = research_agent.generate_book_brief(opportunities[0])

        title = brief["title"]
        db.update_job(job_id, "writing", title=title, meta=brief)
        log.info("Brief ready: '%s'", title)

        # ── 2. WRITE MANUSCRIPT ───────────────────────────────────────────────
        manuscript_dir = config.AUDIOBOOKS_DIR / _slug(title, language)
        manuscript_dir.mkdir(parents=True, exist_ok=True)

        manuscript_path = content_agent.write_full_manuscript(brief, manuscript_dir)

        # ── 3. GENERATE COVER ─────────────────────────────────────────────────
        db.update_job(job_id, "producing")
        cover_path = manuscript_dir / "cover.jpg"
        production_agent.generate_cover(
            brief.get("cover_art_prompt", f"Professional audiobook cover: {title}"),
            cover_path
        )

        # ── 4. CONVERT TO AUDIO ───────────────────────────────────────────────
        audio_dir = manuscript_dir / "audio"
        mp3_files = production_agent.manuscript_to_audiobook(
            manuscript_path, audio_dir, title
        )
        log.info("Audio produced: %d chapters", len(mp3_files))

        # ── 5. SAVE PRODUCT RECORD ────────────────────────────────────────────
        product_id = db.save_product(
            job_id=job_id,
            title=title,
            product_type="audiobook",
            language=language,
            file_path=str(audio_dir),
            platform="gumroad",
            price_usd=brief.get("suggested_price_usd", 14.99),
            meta=brief,
        )

        # ── 6. PACKAGE FOR DISTRIBUTION ───────────────────────────────────────
        # Create a ZIP of all chapter MP3s for Gumroad
        import zipfile
        zip_path = manuscript_dir / f"{_slug(title, language)}_audiobook.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for mp3 in mp3_files:
                zf.write(mp3, mp3.name)

        # ── 7. DISTRIBUTE ─────────────────────────────────────────────────────
        db.update_job(job_id, "distributing")
        product_url = ""
        try:
            product_url = distribution_agent.distribute_product(
                product_id=product_id,
                platform="gumroad",
                product_meta=brief,
                file_path=zip_path,
                cover_path=cover_path,
            )
        except Exception as e:
            log.warning("Gumroad distribution failed: %s", e)

        # ── 8. MARKET ────────────────────────────────────────────────────────
        if product_url:
            db.update_job(job_id, "marketing")
            try:
                marketing_agent.launch_product_marketing(brief, product_url)
            except Exception as e:
                log.warning("Marketing failed: %s", e)

        db.update_job(job_id, "complete")
        log.info("Audiobook pipeline complete: '%s' → %s", title, product_url)

        return {
            "job_id": job_id,
            "product_id": product_id,
            "title": title,
            "language": language,
            "product_url": product_url,
            "audio_files": [str(f) for f in mp3_files],
        }

    except Exception as e:
        db.update_job(job_id, "failed")
        log.exception("Audiobook pipeline failed for job %d: %s", job_id, e)
        raise


def _slug(title: str, lang: str) -> str:
    import re
    s = re.sub(r"[^a-zA-Z0-9]+", "_", title.lower())[:40]
    return f"{s}_{lang}"
