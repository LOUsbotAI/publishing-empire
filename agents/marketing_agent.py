"""
Autonomous customer acquisition:
- Posts to Twitter/X
- Sends Mailchimp email sequences
- Generates SEO metadata
- Writes social captions for all platforms
"""
import json
import logging

import requests
import anthropic
import config

log = logging.getLogger(__name__)
_ai_client = None


def _ai():
    global _ai_client
    if _ai_client is None:
        _ai_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _ai_client


# ─── SOCIAL CONTENT GENERATION ───────────────────────────────────────────────

def generate_social_package(brief: dict, product_url: str) -> dict:
    """Generate a full social media content package for a product launch."""
    prompt = f"""
You are a social media strategist launching this book/product:

Title: {brief['title']}
Subtitle: {brief.get('subtitle', '')}
Niche: {brief.get('niche', '')}
Audience: {brief.get('audience', '')}
Hook: {brief.get('social_hook', '')}
Product URL: {product_url}

Create a JSON launch package with:
- "twitter_posts": array of 7 tweets (max 280 chars each, include URL, vary angles)
- "instagram_caption": long-form IG caption with hashtags (max 2200 chars)
- "linkedin_post": professional post (max 3000 chars)
- "email_subject": compelling email subject line
- "email_body": HTML email body (600 words, includes product URL)
- "hashtags": array of 20 relevant hashtags
- "seo_description": 160-char meta description

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
    return json.loads(raw)


# ─── TWITTER / X ─────────────────────────────────────────────────────────────

def post_to_twitter(text: str, image_path=None) -> str:
    """Post a tweet using Twitter API v2."""
    if not config.TWITTER_API_KEY:
        log.warning("Twitter not configured — skipping post")
        return ""

    import tweepy  # type: ignore
    client = tweepy.Client(
        consumer_key=config.TWITTER_API_KEY,
        consumer_secret=config.TWITTER_API_SECRET,
        access_token=config.TWITTER_ACCESS_TOKEN,
        access_token_secret=config.TWITTER_ACCESS_SECRET,
    )
    response = client.create_tweet(text=text[:280])
    tweet_id = response.data["id"]
    log.info("Tweeted: %s", tweet_id)
    return tweet_id


def run_twitter_campaign(social_package: dict, delay_hours: float = 0) -> list[str]:
    """Post the full Twitter campaign. In production, stagger with a scheduler."""
    tweet_ids = []
    for tweet in social_package.get("twitter_posts", []):
        tweet_id = post_to_twitter(tweet)
        if tweet_id:
            tweet_ids.append(tweet_id)
    return tweet_ids


# ─── EMAIL (MAILCHIMP) ────────────────────────────────────────────────────────

def send_launch_email(subject: str, html_body: str) -> bool:
    """Send a campaign to the entire Mailchimp list."""
    if not config.MAILCHIMP_API_KEY:
        log.warning("Mailchimp not configured — skipping email")
        return False

    base = f"https://{config.MAILCHIMP_SERVER_PREFIX}.api.mailchimp.com/3.0"
    auth = ("anystring", config.MAILCHIMP_API_KEY)

    # Create campaign
    campaign_resp = requests.post(
        f"{base}/campaigns",
        auth=auth,
        json={
            "type": "regular",
            "recipients": {"list_id": config.MAILCHIMP_LIST_ID},
            "settings": {
                "subject_line": subject,
                "from_name": "Publishing Empire",
                "reply_to": "noreply@publishingempire.com",
            },
        },
        timeout=30
    )
    campaign_resp.raise_for_status()
    campaign_id = campaign_resp.json()["id"]

    # Set content
    requests.put(
        f"{base}/campaigns/{campaign_id}/content",
        auth=auth,
        json={"html": html_body},
        timeout=30
    ).raise_for_status()

    # Send
    requests.post(
        f"{base}/campaigns/{campaign_id}/actions/send",
        auth=auth,
        timeout=30
    ).raise_for_status()

    log.info("Launch email sent via Mailchimp, campaign: %s", campaign_id)
    return True


# ─── SEO ─────────────────────────────────────────────────────────────────────

def generate_seo_metadata(brief: dict) -> dict:
    """Generate Amazon/Google SEO optimized metadata."""
    prompt = f"""
Generate SEO-optimized metadata for this book to maximize Amazon and Google discovery:

Title: {brief['title']}
Niche: {brief.get('niche', '')}
Audience: {brief.get('audience', '')}

Return JSON with:
- "amazon_title": keyword-rich title (max 200 chars)
- "amazon_subtitle": keyword-rich subtitle (max 200 chars)
- "amazon_description": HTML description (max 4000 chars, use <b> and <ul>)
- "primary_keywords": array of 7 Amazon backend keywords
- "secondary_keywords": array of 15 long-tail keywords
- "bisac_categories": array of 2 BISAC codes
- "reading_age_from": integer
- "reading_age_to": integer

Return ONLY valid JSON.
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


# ─── FULL LAUNCH ─────────────────────────────────────────────────────────────

def launch_product_marketing(brief: dict, product_url: str) -> dict:
    """Run the complete marketing launch for a new product."""
    log.info("Launching marketing for: %s", brief["title"])

    package = generate_social_package(brief, product_url)
    seo = generate_seo_metadata(brief)

    tweet_ids = run_twitter_campaign(package)

    email_sent = send_launch_email(
        subject=package.get("email_subject", f"New: {brief['title']}"),
        html_body=package.get("email_body", "")
    )

    return {
        "tweets_posted": len(tweet_ids),
        "email_sent": email_sent,
        "seo_metadata": seo,
        "social_package": package,
    }
