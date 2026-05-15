"""
Finds profitable niches, trending topics, and book ideas using AI.
Outputs ranked opportunities for the content pipeline.
"""
import json
import logging
from datetime import datetime
import anthropic
import config

log = logging.getLogger(__name__)
_client = None


def _ai():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def find_opportunities(niches: list[str], language: str = "en", count: int = 5) -> list[dict]:
    """Ask Claude to surface the most profitable book/content opportunities right now."""
    niche_str = ", ".join(niches)
    prompt = f"""
You are a publishing market analyst. Research these niches: {niche_str}

For each of the top {count} opportunities, return a JSON array with objects containing:
- "title": compelling book title
- "niche": which niche
- "type": one of audiobook|ebook|video_series
- "audience": who buys this
- "why_now": why this topic sells right now
- "estimated_monthly_searches": rough Google search volume
- "competition_level": low|medium|high
- "suggested_price_usd": retail price
- "language": "{language}"
- "chapter_outline": array of 8-12 chapter titles

Return ONLY valid JSON array, no markdown, no explanation.
"""
    msg = _ai().messages.create(
        model="claude-opus-4-7",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    opportunities = json.loads(raw)
    log.info("Research found %d opportunities in niches: %s", len(opportunities), niche_str)
    return opportunities


def generate_book_brief(opportunity: dict) -> dict:
    """Expand an opportunity into a full production brief."""
    prompt = f"""
You are a bestselling author and publishing strategist.

Book concept:
Title: {opportunity['title']}
Niche: {opportunity['niche']}
Audience: {opportunity['audience']}
Chapter outline: {json.dumps(opportunity.get('chapter_outline', []))}

Produce a detailed production brief as JSON with:
- "title": final title
- "subtitle": compelling subtitle
- "back_cover_blurb": 150-word sales blurb
- "target_word_count": integer (50000 for full book, 15000 for short read)
- "tone": writing tone description
- "keywords": array of 10 Amazon/SEO keywords
- "categories": array of 3 Amazon categories
- "chapters": array of objects with "title" and "summary" (2-3 sentences each)
- "cover_art_prompt": detailed DALL-E prompt for the cover
- "social_hook": one punchy sentence for social media

Return ONLY valid JSON.
"""
    msg = _ai().messages.create(
        model="claude-opus-4-7",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    brief = json.loads(raw)
    brief["niche"] = opportunity["niche"]
    brief["language"] = opportunity.get("language", "en")
    brief["suggested_price_usd"] = opportunity.get("suggested_price_usd", 9.99)
    brief["type"] = opportunity.get("type", "ebook")
    return brief
