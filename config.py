import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# AI
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROK_API_KEY = os.getenv("GROK_API_KEY", "")

# Audio
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel

# Video
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

# YouTube
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN", "")
YOUTUBE_CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID", "")

# Gumroad
GUMROAD_ACCESS_TOKEN = os.getenv("GUMROAD_ACCESS_TOKEN", "")

# KDP
KDP_EMAIL = os.getenv("KDP_EMAIL", "")
KDP_PASSWORD = os.getenv("KDP_PASSWORD", "")

# Marketing
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY", "")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET", "")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN", "")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET", "")
MAILCHIMP_API_KEY = os.getenv("MAILCHIMP_API_KEY", "")
MAILCHIMP_LIST_ID = os.getenv("MAILCHIMP_LIST_ID", "")
MAILCHIMP_SERVER_PREFIX = os.getenv("MAILCHIMP_SERVER_PREFIX", "us1")

# Stripe
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")

# System behaviour
BOOKS_PER_WEEK = int(os.getenv("BOOKS_PER_WEEK", "3"))
VIDEOS_PER_DAY = int(os.getenv("VIDEOS_PER_DAY", "2"))
TARGET_NICHES = [n.strip() for n in os.getenv("TARGET_NICHES", "self-help,business").split(",")]
PRIMARY_LANGUAGE = os.getenv("PRIMARY_LANGUAGE", "en")
ADDITIONAL_LANGUAGES = [l.strip() for l in os.getenv("ADDITIONAL_LANGUAGES", "es,pt").split(",")]

# Paths
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
AUDIOBOOKS_DIR = OUTPUT_DIR / "audiobooks"
EBOOKS_DIR = OUTPUT_DIR / "ebooks"
VIDEOS_DIR = OUTPUT_DIR / "videos"
COVERS_DIR = OUTPUT_DIR / "covers"
SOCIAL_DIR = OUTPUT_DIR / "social"
LOGS_DIR = BASE_DIR / "logs"

for d in [AUDIOBOOKS_DIR, EBOOKS_DIR, VIDEOS_DIR, COVERS_DIR, SOCIAL_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)
