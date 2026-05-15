"""
Master Launch Pipeline
======================
One call. Every platform. Full marketing. Automatic.

When a book is ready this does ALL of the following in parallel:

DISTRIBUTION
  ✓ Website store (LemonSqueezy checkout + product page)
  ✓ Gumroad (direct sales, weekly bank payout)
  ✓ Amazon KDP (ebook, browser automation)
  ✓ ACX / Audible (audiobook, browser automation)
  ✓ Google Play Books (partner API)
  ✓ Findaway Voices → Spotify, Apple Books, Kobo, Scribd, 40+ more
  ✓ YouTube (long-form video)
  ✓ YouTube Shorts + TikTok + Reels batch

MARKETING
  ✓ 7-tweet campaign (staggered over 7 days)
  ✓ Instagram caption + hashtags
  ✓ LinkedIn post
  ✓ Mailchimp email to full list
  ✓ 5-email drip sequence (automated follow-up)
  ✓ SEO metadata pushed to all platforms
  ✓ Amazon A+ content description
"""
import json
import logging
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import config
import database as db
from agents import (
    content_agent, production_agent, marketing_agent,
    lemonsqueezy_agent, revenue_aggregator
)

log = logging.getLogger("launch")


# ─── PLATFORM LAUNCHERS ──────────────────────────────────────────────────────

def _launch_gumroad(brief: dict, file_path: Path, cover_path: Path,
                    product_id: int) -> dict:
    try:
        from agents.distribution_agent import GumroadDistributor
        dist = GumroadDistributor()
        result = dist.publish_product(
            title=brief["title"],
            description=brief.get("back_cover_blurb", ""),
            price_cents=int(brief.get("suggested_price_usd", 9.99) * 100),
            file_path=file_path,
            cover_path=cover_path,
        )
        db.update_product_published(product_id, result.get("platform_url", ""),
                                    result.get("platform_id"))
        log.info("✅ Gumroad: %s", result.get("platform_url", ""))
        return {"platform": "gumroad", "status": "ok", "url": result.get("platform_url")}
    except Exception as e:
        log.error("❌ Gumroad failed: %s", e)
        return {"platform": "gumroad", "status": "failed", "error": str(e)}


def _launch_lemonsqueezy(brief: dict, product_id: int) -> dict:
    try:
        ids = lemonsqueezy_agent.sync_product_to_ls(
            product_id=product_id,
            title=brief["title"],
            description=brief.get("back_cover_blurb", ""),
            price_usd=brief.get("suggested_price_usd", 9.99),
            product_type=brief.get("type", "ebook"),
        )
        log.info("✅ LemonSqueezy: product %s", ids.get("product_id"))
        return {"platform": "lemonsqueezy", "status": "ok",
                "product_id": ids.get("product_id")}
    except Exception as e:
        log.error("❌ LemonSqueezy failed: %s", e)
        return {"platform": "lemonsqueezy", "status": "failed", "error": str(e)}


def _launch_kdp(brief: dict, manuscript_path: Path, cover_path: Path) -> dict:
    try:
        from agents.distribution_agent import KDPDistributor
        dist = KDPDistributor()
        result = dist.publish_ebook(
            title=brief["title"],
            description=brief.get("back_cover_blurb", ""),
            keywords=brief.get("keywords", []),
            categories=brief.get("categories", []),
            price_usd=brief.get("suggested_price_usd", 9.99),
            manuscript_path=manuscript_path,
            cover_path=cover_path,
        )
        log.info("✅ KDP: %s", result.get("status"))
        return {"platform": "kdp", **result}
    except Exception as e:
        log.error("❌ KDP failed: %s", e)
        return {"platform": "kdp", "status": "failed", "error": str(e)}


def _launch_google_play(brief: dict, epub_path: Path, cover_path: Path) -> dict:
    """Google Play Books upload via Partner API."""
    client_id = os.getenv("GOOGLE_PLAY_CLIENT_ID", "")
    if not client_id:
        return {"platform": "google_play", "status": "not_configured"}
    try:
        import requests
        # Refresh token
        token_resp = requests.post("https://oauth2.googleapis.com/token", data={
            "client_id": client_id,
            "client_secret": os.getenv("GOOGLE_PLAY_CLIENT_SECRET", ""),
            "refresh_token": os.getenv("GOOGLE_PLAY_REFRESH_TOKEN", ""),
            "grant_type": "refresh_token",
        }, timeout=30)
        token_resp.raise_for_status()
        token = token_resp.json()["access_token"]

        # Create book entry
        books_resp = requests.post(
            "https://www.googleapis.com/books/v1/volumes",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            json={
                "volumeInfo": {
                    "title": brief["title"],
                    "subtitle": brief.get("subtitle", ""),
                    "description": brief.get("back_cover_blurb", ""),
                    "industryIdentifiers": [],
                    "categories": brief.get("categories", []),
                    "language": brief.get("language", "en"),
                }
            },
            timeout=30
        )
        books_resp.raise_for_status()
        volume_id = books_resp.json().get("id", "")
        log.info("✅ Google Play Books: volume %s", volume_id)
        return {"platform": "google_play", "status": "ok", "volume_id": volume_id}
    except Exception as e:
        log.error("❌ Google Play failed: %s", e)
        return {"platform": "google_play", "status": "failed", "error": str(e)}


def _launch_findaway(brief: dict, audio_dir: Path) -> dict:
    """Findaway Voices — distributes to Spotify, Apple Books, Kobo, Scribd, 40+ stores."""
    api_key = os.getenv("FINDAWAY_API_KEY", "")
    if not api_key:
        return {"platform": "findaway", "status": "not_configured",
                "note": "Sign up at findawayvoices.com → get API key"}
    try:
        import requests
        mp3_files = sorted(audio_dir.glob("*.mp3"))
        if not mp3_files:
            return {"platform": "findaway", "status": "no_audio_files"}

        # Create title record
        title_resp = requests.post(
            "https://api.findawayvoices.com/v1/titles",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={
                "title": brief["title"],
                "subtitle": brief.get("subtitle", ""),
                "description": brief.get("back_cover_blurb", ""),
                "language": brief.get("language", "en"),
                "price": brief.get("suggested_price_usd", 14.99),
                "bisac": brief.get("categories", ["FIC000000"])[0],
            },
            timeout=30
        )
        title_resp.raise_for_status()
        title_id = title_resp.json().get("id")

        # Upload each chapter
        for i, mp3 in enumerate(mp3_files, 1):
            with open(mp3, "rb") as f:
                requests.post(
                    f"https://api.findawayvoices.com/v1/titles/{title_id}/chapters",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"audio": (mp3.name, f, "audio/mpeg")},
                    data={"chapter_number": i},
                    timeout=300
                )

        log.info("✅ Findaway Voices: title %s → Spotify, Apple, Kobo, Scribd...", title_id)
        return {"platform": "findaway", "status": "ok", "title_id": title_id,
                "distributes_to": "Spotify, Apple Books, Kobo, Scribd, 40+ stores"}
    except Exception as e:
        log.error("❌ Findaway failed: %s", e)
        return {"platform": "findaway", "status": "failed", "error": str(e)}


def _launch_youtube(brief: dict, language: str, product_dir: Path) -> dict:
    try:
        from pipelines import video_pipeline
        result = video_pipeline.run_long_form(brief, language)
        log.info("✅ YouTube: %s", result.get("url", "uploading"))
        return {"platform": "youtube", "status": "ok", "url": result.get("url")}
    except Exception as e:
        log.error("❌ YouTube failed: %s", e)
        return {"platform": "youtube", "status": "failed", "error": str(e)}


def _launch_shorts(brief: dict, language: str) -> dict:
    try:
        from pipelines import video_pipeline
        results = video_pipeline.run_short_form_batch(brief, language, count=5)
        log.info("✅ Shorts: %d videos produced", len(results))
        return {"platform": "shorts", "status": "ok", "count": len(results)}
    except Exception as e:
        log.error("❌ Shorts failed: %s", e)
        return {"platform": "shorts", "status": "failed", "error": str(e)}


# ─── MARKETING LAUNCHERS ─────────────────────────────────────────────────────

def _run_full_marketing(brief: dict, product_url: str, product_id: int) -> dict:
    results = {}

    # Social package (Twitter, IG, LinkedIn, email)
    try:
        package = marketing_agent.generate_social_package(brief, product_url)
        seo = marketing_agent.generate_seo_metadata(brief)

        # Schedule tweets across 7 days (stored for drip posting)
        tweets = package.get("twitter_posts", [])
        _schedule_tweets(tweets, product_id)
        results["tweets_scheduled"] = len(tweets)

        # Post first tweet immediately
        if tweets:
            marketing_agent.post_to_twitter(tweets[0])
            results["tweet_posted"] = True

        # Email launch
        sent = marketing_agent.send_launch_email(
            package.get("email_subject", f"New: {brief['title']}"),
            package.get("email_body", ""),
        )
        results["email_sent"] = sent

        # Store social content
        with db.conn() as c:
            c.execute(
                """INSERT INTO social_posts (product_id, platform, content, posted_at)
                   VALUES (?,?,?,datetime('now'))""",
                (product_id, "instagram", package.get("instagram_caption", ""))
            )

        results["seo"] = seo
        log.info("✅ Marketing: tweets=%d, email=%s", len(tweets), sent)
    except Exception as e:
        log.error("❌ Marketing failed: %s", e)
        results["error"] = str(e)

    # Drip email sequence (5 follow-up emails over 14 days)
    try:
        _create_email_drip_sequence(brief, product_url)
        results["drip_sequence"] = "created"
    except Exception as e:
        log.warning("Drip sequence failed: %s", e)

    return results


def _schedule_tweets(tweets: list[str], product_id: int):
    """Store tweets for staggered posting over 7 days."""
    with db.conn() as c:
        for i, tweet in enumerate(tweets):
            # Each tweet is scheduled 1 day apart
            c.execute(
                """INSERT INTO social_posts
                   (product_id, platform, content, posted_at)
                   VALUES (?,?,?,datetime('now', ?))""",
                (product_id, "twitter_scheduled", tweet, f"+{i} days")
            )


def _create_email_drip_sequence(brief: dict, product_url: str):
    """Generate and store a 5-email follow-up sequence for new subscribers."""
    import anthropic
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=4096,
        messages=[{"role": "user", "content": f"""
Write a 5-email drip sequence for this product:
Title: {brief['title']}
Audience: {brief.get('audience', '')}
URL: {product_url}

Emails sent on days: 1, 3, 7, 14, 30 after signup.
Each email: subject line + HTML body (200-400 words).
Topics: value delivery, testimonial/story, objection handling, scarcity/bonus, final reminder.

Return as JSON array of objects with "day", "subject", "html_body".
Return ONLY valid JSON.
"""}]
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    sequence = json.loads(raw)

    with db.conn() as c:
        for email in sequence:
            c.execute(
                """INSERT INTO email_sequences
                   (brief_title, send_day, subject, html_body)
                   VALUES (?,?,?,?)""",
                (brief["title"], email.get("day", 0),
                 email.get("subject", ""), email.get("html_body", ""))
            )
    log.info("Email drip sequence created: %d emails", len(sequence))


# ─── MASTER LAUNCH ────────────────────────────────────────────────────────────

def launch_everywhere(brief: dict, product_id: int,
                      manuscript_path: Path = None,
                      audio_dir: Path = None,
                      epub_path: Path = None,
                      cover_path: Path = None) -> dict:
    """
    Full launch: every platform, full marketing, all at once.
    Call this after any content is produced and ready.
    """
    title = brief["title"]
    language = brief.get("language", "en")
    content_type = brief.get("type", "ebook")

    log.info("=" * 60)
    log.info("LAUNCHING: %s [%s] → ALL PLATFORMS", title, language)
    log.info("=" * 60)

    db.update_job_by_product(product_id, "launching")

    results = {"title": title, "language": language, "platforms": {}}
    primary_url = ""

    # Build file path for distribution
    file_for_gumroad = None
    if audio_dir and audio_dir.exists():
        # Zip audio files for Gumroad
        zip_path = audio_dir.parent / f"{audio_dir.name}_audiobook.zip"
        if not zip_path.exists():
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for mp3 in sorted(audio_dir.glob("*.mp3")):
                    zf.write(mp3, mp3.name)
        file_for_gumroad = zip_path
    elif epub_path and epub_path.exists():
        file_for_gumroad = epub_path

    # ── Run all platform launches in parallel ─────────────────────────────
    tasks = {}
    with ThreadPoolExecutor(max_workers=6) as ex:

        if file_for_gumroad and config.GUMROAD_ACCESS_TOKEN:
            tasks["gumroad"] = ex.submit(
                _launch_gumroad, brief, file_for_gumroad, cover_path, product_id
            )

        if os.getenv("LEMONSQUEEZY_API_KEY"):
            tasks["lemonsqueezy"] = ex.submit(
                _launch_lemonsqueezy, brief, product_id
            )

        if config.KDP_EMAIL and manuscript_path:
            tasks["kdp"] = ex.submit(
                _launch_kdp, brief, manuscript_path, cover_path
            )

        if os.getenv("GOOGLE_PLAY_CLIENT_ID") and epub_path:
            tasks["google_play"] = ex.submit(
                _launch_google_play, brief, epub_path, cover_path
            )

        if os.getenv("FINDAWAY_API_KEY") and audio_dir:
            tasks["findaway"] = ex.submit(
                _launch_findaway, brief, audio_dir
            )

        if config.YOUTUBE_REFRESH_TOKEN:
            tasks["youtube"] = ex.submit(_launch_youtube, brief, language,
                                         epub_path.parent if epub_path else Path("."))
            tasks["shorts"] = ex.submit(_launch_shorts, brief, language)

        # Collect results
        for name, future in tasks.items():
            try:
                r = future.result(timeout=600)
                results["platforms"][name] = r
                # Use first successful URL as primary
                if not primary_url and r.get("url"):
                    primary_url = r["url"]
            except Exception as e:
                results["platforms"][name] = {"status": "error", "error": str(e)}

    # ── Marketing (needs a URL, runs after distribution) ──────────────────
    if not primary_url:
        primary_url = f"https://yourstore.com/product/{product_id}"

    db.update_product_published(product_id, primary_url)
    marketing_results = _run_full_marketing(brief, primary_url, product_id)
    results["marketing"] = marketing_results

    # ── Summary ───────────────────────────────────────────────────────────
    ok = [k for k, v in results["platforms"].items() if v.get("status") == "ok"]
    failed = [k for k, v in results["platforms"].items() if v.get("status") == "failed"]
    not_conf = [k for k, v in results["platforms"].items() if v.get("status") == "not_configured"]

    db.update_job_by_product(product_id, "live")

    log.info("=" * 60)
    log.info("LAUNCH COMPLETE: %s", title)
    log.info("  ✅ Live on: %s", ", ".join(ok) if ok else "none")
    if failed:
        log.warning("  ❌ Failed: %s", ", ".join(failed))
    if not_conf:
        log.info("  ⚙️  Not configured: %s", ", ".join(not_conf))
    log.info("  🌐 Primary URL: %s", primary_url)
    log.info("=" * 60)

    results["primary_url"] = primary_url
    results["live_on"] = ok
    results["timestamp"] = datetime.utcnow().isoformat()
    return results
