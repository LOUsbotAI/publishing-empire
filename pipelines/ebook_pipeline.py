"""
Full autonomous ebook pipeline:
Research → Write → Format → Cover → Distribute (Gumroad + KDP) → Market
"""
import logging
from pathlib import Path

import config
import database as db
from agents import research_agent, content_agent, production_agent, distribution_agent, marketing_agent

log = logging.getLogger(__name__)


def run(niche: str = None, language: str = None, brief: dict = None) -> dict:
    niche = niche or config.TARGET_NICHES[0]
    language = language or config.PRIMARY_LANGUAGE

    job_id = db.create_job("ebook", niche, language)
    log.info("Ebook job %d started", job_id)

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

        # ── 2. WRITE ──────────────────────────────────────────────────────────
        book_dir = config.EBOOKS_DIR / _slug(title, language)
        book_dir.mkdir(parents=True, exist_ok=True)

        manuscript_path = content_agent.write_full_manuscript(brief, book_dir)

        # ── 3. COVER ──────────────────────────────────────────────────────────
        db.update_job(job_id, "producing")
        cover_path = book_dir / "cover.jpg"
        production_agent.generate_cover(
            brief.get("cover_art_prompt", f"Professional ebook cover: {title}"),
            cover_path
        )

        # ── 4. FORMAT ─────────────────────────────────────────────────────────
        epub_path = production_agent.manuscript_to_epub(manuscript_path, book_dir, title)
        pdf_path = production_agent.manuscript_to_pdf(manuscript_path, book_dir)

        # ── 5. SAVE PRODUCT RECORD ────────────────────────────────────────────
        product_id = db.save_product(
            job_id=job_id,
            title=title,
            product_type="ebook",
            language=language,
            file_path=str(epub_path),
            platform="gumroad",
            price_usd=brief.get("suggested_price_usd", 9.99),
            meta=brief,
        )

        # ── 6. DISTRIBUTE ─────────────────────────────────────────────────────
        db.update_job(job_id, "distributing")
        product_url = ""
        try:
            product_url = distribution_agent.distribute_product(
                product_id=product_id,
                platform="gumroad",
                product_meta=brief,
                file_path=epub_path,
                cover_path=cover_path,
            )
        except Exception as e:
            log.warning("Gumroad failed: %s", e)

        # Also attempt KDP if credentials available
        if config.KDP_EMAIL and config.KDP_PASSWORD:
            try:
                distribution_agent.distribute_product(
                    product_id=product_id,
                    platform="kdp",
                    product_meta=brief,
                    file_path=manuscript_path,
                    cover_path=cover_path,
                )
            except Exception as e:
                log.warning("KDP failed: %s", e)

        # ── 7. MARKET ────────────────────────────────────────────────────────
        if product_url:
            db.update_job(job_id, "marketing")
            try:
                marketing_agent.launch_product_marketing(brief, product_url)
            except Exception as e:
                log.warning("Marketing failed: %s", e)

        db.update_job(job_id, "complete")
        log.info("Ebook pipeline complete: '%s' → %s", title, product_url)

        return {
            "job_id": job_id,
            "product_id": product_id,
            "title": title,
            "language": language,
            "epub": str(epub_path),
            "pdf": str(pdf_path) if pdf_path else None,
            "product_url": product_url,
        }

    except Exception as e:
        db.update_job(job_id, "failed")
        log.exception("Ebook pipeline failed for job %d: %s", job_id, e)
        raise


def _slug(title: str, lang: str) -> str:
    import re
    s = re.sub(r"[^a-zA-Z0-9]+", "_", title.lower())[:40]
    return f"{s}_{lang}"
