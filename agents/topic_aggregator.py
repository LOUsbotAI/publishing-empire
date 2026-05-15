"""
Topic Aggregator
================
Multi-source trending topic discovery — no Reddit dependency.

Sources (in priority order):
  1. Hacker News API  — free, reliable, tech/business focused
  2. Dev.to API       — developer content, free API
  3. ProductHunt API  — product launches (requires token)
  4. RSS feeds        — curated high-signal blogs
  5. Cached fallback  — never fails, rotates from saved topics

Each topic is scored by engagement and filtered for publishable niches.
Outputs INSERT-ready topic briefs for the production queue.

Replaces fetch_topics.js which returns HTTP 403 from Reddit.
"""
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
import database as db
import config

log = logging.getLogger("topic_aggregator")

CACHE_PATH = Path("logs/topic_cache.json")
CACHE_TTL_HOURS = 6

# Niche keywords — topics matching these are boosted
NICHE_KEYWORDS = {
    "self-help":     ["productivity", "habits", "mindset", "discipline", "focus", "morning routine",
                      "goal setting", "self improvement", "mental health", "confidence"],
    "finance":       ["passive income", "investing", "stocks", "crypto", "savings", "budget",
                      "financial freedom", "real estate", "side hustle", "wealth"],
    "business":      ["startup", "saas", "entrepreneurship", "marketing", "sales", "growth hacking",
                      "ai business", "automation", "founder", "product launch"],
    "health":        ["fitness", "nutrition", "mental health", "meditation", "longevity", "sleep",
                      "exercise", "diet", "wellness", "biohacking"],
    "technology":    ["ai", "machine learning", "python", "programming", "llm", "gpt", "automation",
                      "software", "developer", "open source"],
    "true-crime":    ["crime", "mystery", "investigation", "case", "serial killer", "fraud", "scam"],
}


# ─── HACKER NEWS ─────────────────────────────────────────────────────────────

def _fetch_hackernews(count: int = 30) -> list[dict]:
    """Pull top stories from Hacker News Algolia API."""
    try:
        r = requests.get(
            "https://hn.algolia.com/api/v1/search",
            params={
                "tags": "story",
                "numericFilters": "points>50,num_comments>10",
                "hitsPerPage": count,
            },
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 Publishing-Research-Bot/1.0"},
        )
        r.raise_for_status()
        hits = r.json().get("hits", [])
        topics = []
        for h in hits:
            if not h.get("title"):
                continue
            topics.append({
                "title": h["title"],
                "url": h.get("url", ""),
                "score": h.get("points", 0) + h.get("num_comments", 0) * 2,
                "source": "hackernews",
                "created_at": h.get("created_at", ""),
            })
        log.info("HackerNews: fetched %d topics", len(topics))
        return topics
    except Exception as e:
        log.warning("HackerNews fetch failed: %s", e)
        return []


# ─── DEV.TO ──────────────────────────────────────────────────────────────────

def _fetch_devto(count: int = 20) -> list[dict]:
    """Pull trending articles from Dev.to API (free, no auth needed)."""
    try:
        r = requests.get(
            "https://dev.to/api/articles",
            params={"top": 7, "per_page": count},
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 Publishing-Research-Bot/1.0"},
        )
        r.raise_for_status()
        articles = r.json()
        topics = []
        for a in articles:
            if not a.get("title"):
                continue
            topics.append({
                "title": a["title"],
                "url": a.get("url", ""),
                "score": a.get("positive_reactions_count", 0) + a.get("comments_count", 0) * 3,
                "source": "devto",
                "tags": a.get("tag_list", []),
                "created_at": a.get("published_at", ""),
            })
        log.info("Dev.to: fetched %d topics", len(topics))
        return topics
    except Exception as e:
        log.warning("Dev.to fetch failed: %s", e)
        return []


# ─── RSS FEEDS ───────────────────────────────────────────────────────────────

RSS_FEEDS = [
    ("https://feeds.feedburner.com/entrepreneur/latest", "business"),
    ("https://www.inc.com/rss/", "business"),
    ("https://feeds.feedburner.com/TechCrunch", "technology"),
    ("https://feeds.feedburner.com/HealthDay", "health"),
    ("https://www.psychologytoday.com/intl/front-page/feed", "self-help"),
    ("https://feeds.feedburner.com/typepad/kranz", "finance"),
]

def _fetch_rss(count_per_feed: int = 5) -> list[dict]:
    """Parse curated RSS feeds for publishable topics."""
    try:
        import xml.etree.ElementTree as ET
    except ImportError:
        return []

    topics = []
    for feed_url, niche in RSS_FEEDS:
        try:
            r = requests.get(feed_url, timeout=10,
                             headers={"User-Agent": "Mozilla/5.0 Publishing-Research-Bot/1.0"})
            if r.status_code != 200:
                continue
            root = ET.fromstring(r.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            # RSS 2.0
            items = root.findall(".//item")[:count_per_feed]
            for item in items:
                title_el = item.find("title")
                link_el = item.find("link")
                if title_el is None or not title_el.text:
                    continue
                topics.append({
                    "title": title_el.text.strip(),
                    "url": link_el.text.strip() if link_el is not None else "",
                    "score": 30,
                    "source": "rss",
                    "niche_hint": niche,
                    "created_at": datetime.utcnow().isoformat(),
                })
        except Exception:
            continue

    log.info("RSS feeds: fetched %d topics", len(topics))
    return topics


# ─── FALLBACK CACHE ───────────────────────────────────────────────────────────

EVERGREEN_TOPICS = [
    "10 Habits of Highly Productive People",
    "How to Build Passive Income in 2026",
    "The Beginner's Guide to Investing in ETFs",
    "Mindfulness Techniques for Busy Professionals",
    "Python Automation for Non-Programmers",
    "How AI is Changing the Publishing Industry",
    "The Complete Guide to Financial Freedom",
    "Building a Side Hustle While Working Full-Time",
    "Sleep Optimization: Science-Backed Techniques",
    "How to Write and Publish a Book in 30 Days",
    "Digital Minimalism: Reclaim Your Focus",
    "The Psychology of Motivation and Habit Formation",
    "Crypto for Beginners: What You Need to Know",
    "How to Negotiate a Higher Salary",
    "The Freelancer's Guide to Taxes and Finance",
]

def _fallback_topics() -> list[dict]:
    """Return evergreen topics when all APIs fail."""
    log.info("Using evergreen fallback topics")
    return [
        {"title": t, "url": "", "score": 20, "source": "fallback",
         "created_at": datetime.utcnow().isoformat()}
        for t in EVERGREEN_TOPICS
    ]


# ─── SCORING & FILTERING ──────────────────────────────────────────────────────

def _score_topic(topic: dict, target_niches: list[str]) -> dict:
    """Score a topic for publishability. Higher = better match."""
    title_lower = topic["title"].lower()
    base_score = topic.get("score", 0)
    niche_bonus = 0
    matched_niche = topic.get("niche_hint", "general")

    for niche in target_niches:
        keywords = NICHE_KEYWORDS.get(niche, [])
        matches = sum(1 for kw in keywords if kw in title_lower)
        if matches > 0:
            niche_bonus += matches * 15
            matched_niche = niche

    # Penalize very short titles (likely clickbait)
    if len(topic["title"]) < 20:
        base_score = max(0, base_score - 20)

    # Boost how-to, guide, tips, complete
    for boost_word in ["how to", "guide", "tips", "ways to", "complete", "best", "ultimate"]:
        if boost_word in title_lower:
            base_score += 10

    topic["final_score"] = base_score + niche_bonus
    topic["matched_niche"] = matched_niche
    return topic


def _is_too_similar(title: str, existing: list[str], threshold: float = 0.7) -> bool:
    """Simple word-overlap check to avoid near-duplicate topics."""
    words = set(title.lower().split())
    for existing_title in existing:
        existing_words = set(existing_title.lower().split())
        if not existing_words:
            continue
        overlap = len(words & existing_words) / max(len(words), len(existing_words))
        if overlap > threshold:
            return True
    return False


# ─── CACHE ───────────────────────────────────────────────────────────────────

def _load_cache() -> list[dict]:
    if CACHE_PATH.exists():
        try:
            data = json.loads(CACHE_PATH.read_text())
            age_hours = (time.time() - data.get("ts", 0)) / 3600
            if age_hours < CACHE_TTL_HOURS:
                return data.get("topics", [])
        except Exception:
            pass
    return []


def _save_cache(topics: list[dict]):
    CACHE_PATH.parent.mkdir(exist_ok=True)
    CACHE_PATH.write_text(json.dumps({"ts": time.time(), "topics": topics}))


# ─── MAIN ────────────────────────────────────────────────────────────────────

def fetch_topics(count: int = 20, use_cache: bool = True) -> list[dict]:
    """
    Fetch trending topics from all available sources.
    Returns top `count` scored topics ready for book production.
    """
    target_niches = [n.strip() for n in
                     os.getenv("TARGET_NICHES", "self-help,business,finance").split(",")]

    # Try cache first
    if use_cache:
        cached = _load_cache()
        if cached:
            log.info("Using cached topics (%d available)", len(cached))
            return cached[:count]

    # Fetch from all sources in parallel
    from concurrent.futures import ThreadPoolExecutor
    all_raw = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = [
            ex.submit(_fetch_hackernews, 40),
            ex.submit(_fetch_devto, 20),
            ex.submit(_fetch_rss, 5),
        ]
        for f in futures:
            try:
                all_raw.extend(f.result(timeout=20))
            except Exception as e:
                log.warning("Source fetch timed out: %s", e)

    # Fallback if all fail
    if not all_raw:
        all_raw = _fallback_topics()

    # Score and deduplicate
    scored = [_score_topic(t, target_niches) for t in all_raw]
    scored.sort(key=lambda x: x["final_score"], reverse=True)

    seen_titles = []
    unique = []
    for t in scored:
        if not _is_too_similar(t["title"], seen_titles):
            seen_titles.append(t["title"])
            unique.append(t)
        if len(unique) >= count * 2:  # collect 2× and trim to `count`
            break

    result = unique[:count]
    _save_cache(result)
    log.info("Topic aggregator: %d unique topics from %d raw (sources: HN, Dev.to, RSS)",
             len(result), len(all_raw))
    return result


def queue_topics_for_production(count: int = 20) -> int:
    """
    Fetch topics and insert them as pending production jobs.
    Returns number of new jobs created.
    """
    topics = fetch_topics(count=count, use_cache=False)
    created = 0
    for t in topics:
        try:
            db.create_job(
                pipeline="both",
                niche=t.get("matched_niche", "general"),
                language=config.PRIMARY_LANGUAGE,
                meta={
                    "title": t["title"],
                    "source_url": t.get("url", ""),
                    "source": t.get("source", "aggregator"),
                    "score": t.get("final_score", 0),
                    "aggregated_at": datetime.utcnow().isoformat(),
                },
            )
            created += 1
        except Exception as e:
            log.error("Failed to queue topic '%s': %s", t["title"], e)

    log.info("Queued %d/%d topics for production", created, len(topics))
    return created
