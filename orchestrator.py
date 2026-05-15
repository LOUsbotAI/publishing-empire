"""
Publishing Empire Orchestrator
================================
Runs autonomously — schedules all pipelines, syncs revenue, posts reports.

Usage:
    python orchestrator.py          # run forever
    python orchestrator.py once     # run one full cycle now (testing)
    python orchestrator.py report   # print revenue report
"""
import os
import sys
import logging
import json
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/orchestrator.log", encoding="utf-8"),
    ]
)
log = logging.getLogger("orchestrator")

import config
import database as db
from agents import finance_agent, stripe_agent, heartbeat_agent, payout_agent, revenue_aggregator, tax_agent
from pipelines import audiobook_pipeline, ebook_pipeline, video_pipeline, full_book_pipeline
from agents import research_agent


def research_and_queue():
    """Find new opportunities and create jobs for all niches × all languages."""
    log.info("Running market research across %d niches", len(config.TARGET_NICHES))
    all_languages = [config.PRIMARY_LANGUAGE] + config.ADDITIONAL_LANGUAGES

    for niche in config.TARGET_NICHES:
        try:
            opportunities = research_agent.find_opportunities(
                [niche], config.PRIMARY_LANGUAGE, count=2
            )
            for opp in opportunities:
                brief = research_agent.generate_book_brief(opp)
                # Queue the primary language
                db.create_job(
                    pipeline="both",  # produce ebook + audiobook, launch everywhere
                    niche=niche,
                    language=config.PRIMARY_LANGUAGE,
                    meta=brief,
                )
                # Queue the same book in every additional language automatically
                for lang in config.ADDITIONAL_LANGUAGES:
                    lang_brief = dict(brief, language=lang)
                    db.create_job(
                        pipeline="both",
                        niche=niche,
                        language=lang,
                        meta=lang_brief,
                    )
        except Exception as e:
            log.error("Research failed for niche '%s': %s", niche, e)


def process_pending_jobs(max_jobs: int = 5):
    """Pick up pending jobs and run them."""
    jobs = db.get_pending_jobs()[:max_jobs]
    log.info("Processing %d pending jobs", len(jobs))

    for job in jobs:
        pipeline = job["pipeline"]
        language = job["language"]
        niche = job["niche"]
        meta = json.loads(job["meta"]) if job["meta"] else None

        log.info("Running job %d: %s (%s/%s)", job["id"], pipeline, niche, language)
        try:
            # All content jobs go through the full pipeline:
            # research → write → produce → launch on ALL platforms → full marketing
            if pipeline in ("audiobook",):
                full_book_pipeline.run(niche, language, brief=meta, content_type="audiobook")
            elif pipeline in ("ebook", "short_read"):
                full_book_pipeline.run(niche, language, brief=meta, content_type="ebook")
            elif pipeline in ("video_series", "video_long", "video_short"):
                if meta:
                    video_pipeline.run_long_form(meta, language)
                    video_pipeline.run_short_form_batch(meta, language)
            else:
                # Default: produce both ebook + audiobook, launch everywhere
                full_book_pipeline.run(niche, language, brief=meta, content_type="both")
        except Exception as e:
            log.error("Job %d failed: %s", job["id"], e)


def revenue_sync_and_report():
    """Pull revenue from all platforms and log daily summary."""
    finance_agent.sync_all_revenue()
    report = finance_agent.daily_report()
    log.info(
        "REVENUE REPORT | Total: $%.2f | Products: %d",
        report["total_revenue_usd"],
        report["total_published_products"]
    )
    report_path = config.LOGS_DIR / f"report_{datetime.utcnow().strftime('%Y%m%d')}.json"
    import json as _json
    report_path.write_text(_json.dumps(report, indent=2), encoding="utf-8")
    return report


def produce_daily_videos():
    """Produce short-form video content for the day's top books."""
    with db.conn() as c:
        recent = c.execute(
            """SELECT meta FROM products WHERE type IN ('audiobook','ebook')
               AND published_at IS NOT NULL ORDER BY published_at DESC LIMIT 3"""
        ).fetchall()

    import json as _json
    for row in recent:
        try:
            brief = _json.loads(row["meta"])
            video_pipeline.run_short_form_batch(brief, count=config.VIDEOS_PER_DAY)
        except Exception as e:
            log.error("Daily video production failed: %s", e)


# ─── SCHEDULES ───────────────────────────────────────────────────────────────

def startup_health_check():
    """Validate critical API keys before the scheduler starts. Raises on failure."""
    import anthropic
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            messages=[{"role": "user", "content": "ping"}],
        )
        log.info("✓ Anthropic API — live")
    except Exception as e:
        raise RuntimeError(
            f"Anthropic API check failed: {e}\n"
            "Run: python3 scripts/validate_content.py"
        ) from e

    if not config.ELEVENLABS_API_KEY:
        log.warning("⚠ ELEVENLABS_API_KEY not set — audiobooks will be silent stubs")
    if not config.GEMINI_API_KEY:
        log.warning("⚠ GEMINI_API_KEY not set — Gemini features disabled")
    if not config.STRIPE_SECRET_KEY:
        log.warning("⚠ STRIPE_SECRET_KEY not set — Stripe sync disabled")


def run_forever():
    """Main loop — runs the empire indefinitely."""
    from apscheduler.schedulers.blocking import BlockingScheduler  # type: ignore
    from apscheduler.triggers.cron import CronTrigger

    db.init_db()
    startup_health_check()
    scheduler = BlockingScheduler(timezone="UTC")

    # Research new books — twice a week (Mon + Thu at 06:00 UTC)
    scheduler.add_job(research_and_queue, CronTrigger(day_of_week="mon,thu", hour=6))

    # Topic aggregator — every 2 hours from all sources (HN, Dev.to, RSS)
    # Replaces Reddit-based fetching which returns 403
    from agents import topic_aggregator
    scheduler.add_job(
        topic_aggregator.queue_topics_for_production,
        CronTrigger(hour="*/2"),
        kwargs={"count": 20},
    )

    # Process pending jobs — every 4 hours
    scheduler.add_job(process_pending_jobs, CronTrigger(hour="*/4"), kwargs={"max_jobs": 3})

    # Daily short-form videos — every day at 08:00 UTC
    scheduler.add_job(produce_daily_videos, CronTrigger(hour=8))

    # Revenue sync — every day at 23:00 UTC
    scheduler.add_job(revenue_sync_and_report, CronTrigger(hour=23))

    # Stripe product sync — every hour (publish new products to Stripe automatically)
    scheduler.add_job(stripe_agent.sync_all_products_to_stripe, CronTrigger(minute=0))

    # Heartbeat — every 5 minutes
    scheduler.add_job(heartbeat_agent.run_heartbeat, "interval", minutes=5)

    # Scan imports/ for Termux export packs — every 30 minutes
    from agents import pack_importer
    scheduler.add_job(pack_importer.scan_imports_folder, "interval", minutes=30)

    # Payout threshold check — every 6 hours (pays out when balance > $50)
    scheduler.add_job(
        payout_agent.check_and_payout_threshold,
        "interval", hours=6,
        kwargs={"threshold_usd": float(os.getenv("PAYOUT_THRESHOLD_USD", "50"))}
    )

    # Failed payout alert — daily at 07:00 UTC (catches bank account issues immediately)
    scheduler.add_job(payout_agent.check_for_failed_payouts, CronTrigger(hour=7))

    # Cross-platform revenue sync — every 6 hours
    scheduler.add_job(revenue_aggregator.full_revenue_report, "interval", hours=6)

    # Quarterly BAS (Australian GST return) — 1st of month after quarter end
    # Q1 (Jul-Sep) → 1 Oct | Q2 (Oct-Dec) → 1 Jan | Q3 (Jan-Mar) → 1 Apr | Q4 (Apr-Jun) → 1 Jul
    scheduler.add_job(
        tax_agent.generate_bas,
        CronTrigger(month="1,4,7,10", day=1, hour=9),
        kwargs={"entity": "lucorp"}
    )
    # Annual tax summary — 1 July each year (start of new AU financial year)
    scheduler.add_job(
        tax_agent.annual_tax_summary,
        CronTrigger(month=7, day=1, hour=10)
    )

    log.info("=" * 60)
    log.info("Publishing Empire is LIVE — running autonomously")
    log.info("Books/week target: %d | Videos/day target: %d",
             config.BOOKS_PER_WEEK, config.VIDEOS_PER_DAY)
    log.info("Target niches: %s", ", ".join(config.TARGET_NICHES))
    log.info("Languages: %s", ", ".join([config.PRIMARY_LANGUAGE] + config.ADDITIONAL_LANGUAGES))
    log.info("=" * 60)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Orchestrator stopped")


def run_once():
    """Run one complete cycle immediately — useful for testing."""
    db.init_db()
    log.info("Running one full cycle...")
    research_and_queue()
    process_pending_jobs(max_jobs=1)
    revenue_sync_and_report()
    log.info("One-cycle run complete.")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "forever"

    if arg == "once":
        run_once()
    elif arg == "report":
        db.init_db()
        report = revenue_sync_and_report()
        import json as _json
        print(_json.dumps(report, indent=2))
    elif arg == "research":
        db.init_db()
        research_and_queue()
    else:
        run_forever()
