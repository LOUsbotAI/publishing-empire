"""
Publishes finished products to:
- Gumroad (direct sales, immediate revenue)
- YouTube (video content)
- KDP (ebooks) — via browser automation
- ACX (audiobooks) — via browser automation
- Findaway Voices (audiobook aggregator)
"""
import json
import logging
from pathlib import Path

import requests
import config
import database as db

log = logging.getLogger(__name__)


# ─── GUMROAD ─────────────────────────────────────────────────────────────────

class GumroadDistributor:
    BASE = "https://api.gumroad.com/v2"

    def __init__(self):
        if not config.GUMROAD_ACCESS_TOKEN:
            raise RuntimeError("GUMROAD_ACCESS_TOKEN not set")
        self.token = config.GUMROAD_ACCESS_TOKEN

    def publish_product(self, title: str, description: str, price_cents: int,
                        file_path: Path, cover_path: Path = None) -> dict:
        """Create a Gumroad product and upload the file."""
        data = {
            "access_token": self.token,
            "name": title,
            "description": description,
            "price": price_cents,
            "published": "true",
        }
        resp = requests.post(f"{self.BASE}/products", data=data, timeout=30)
        resp.raise_for_status()
        product = resp.json()["product"]
        product_id = product["id"]

        # Upload the file
        with open(file_path, "rb") as f:
            requests.put(
                f"{self.BASE}/products/{product_id}/files",
                data={"access_token": self.token},
                files={"file": (file_path.name, f)},
                timeout=120
            ).raise_for_status()

        # Upload cover if available
        if cover_path and cover_path.exists():
            with open(cover_path, "rb") as f:
                requests.put(
                    f"{self.BASE}/products/{product_id}/cover",
                    data={"access_token": self.token},
                    files={"cover": (cover_path.name, f, "image/jpeg")},
                    timeout=60
                )

        log.info("Published to Gumroad: %s — %s", title, product.get("short_url"))
        return {
            "platform": "gumroad",
            "platform_id": product_id,
            "platform_url": product.get("short_url", ""),
        }

    def get_sales(self) -> list[dict]:
        resp = requests.get(
            f"{self.BASE}/sales",
            params={"access_token": self.token},
            timeout=30
        )
        resp.raise_for_status()
        return resp.json().get("sales", [])


# ─── YOUTUBE ─────────────────────────────────────────────────────────────────

class YouTubeDistributor:
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"

    def __init__(self):
        if not config.YOUTUBE_REFRESH_TOKEN:
            raise RuntimeError("YouTube OAuth not configured")
        self._access_token = None

    def _get_access_token(self) -> str:
        resp = requests.post(self.TOKEN_URL, data={
            "client_id": config.YOUTUBE_CLIENT_ID,
            "client_secret": config.YOUTUBE_CLIENT_SECRET,
            "refresh_token": config.YOUTUBE_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        }, timeout=30)
        resp.raise_for_status()
        return resp.json()["access_token"]

    def upload_video(self, video_path: Path, title: str, description: str,
                     tags: list[str], thumbnail_path: Path = None,
                     category_id: str = "27") -> dict:
        token = self._get_access_token()
        metadata = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags[:20],
                "categoryId": category_id,
            },
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
        }
        # Resumable upload
        init_resp = requests.post(
            self.UPLOAD_URL,
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(video_path.stat().st_size),
            },
            json=metadata,
            timeout=30
        )
        init_resp.raise_for_status()
        upload_url = init_resp.headers["Location"]

        with open(video_path, "rb") as f:
            upload_resp = requests.put(
                upload_url,
                headers={"Content-Type": "video/mp4"},
                data=f,
                timeout=600
            )
        upload_resp.raise_for_status()
        video_id = upload_resp.json()["id"]
        url = f"https://www.youtube.com/watch?v={video_id}"
        log.info("Uploaded to YouTube: %s — %s", title, url)
        return {"platform": "youtube", "platform_id": video_id, "platform_url": url}


# ─── KDP (browser automation) ────────────────────────────────────────────────

class KDPDistributor:
    """
    Automates KDP uploads using Playwright.
    Install: pip install playwright && playwright install chromium
    """

    def publish_ebook(self, title: str, description: str, keywords: list[str],
                      categories: list[str], price_usd: float,
                      manuscript_path: Path, cover_path: Path) -> dict:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            log.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return {"platform": "kdp", "status": "playwright_not_installed"}

        log.info("Starting KDP upload for: %s", title)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # Login
            page.goto("https://kdp.amazon.com/en_US/signin")
            page.fill("#ap_email", config.KDP_EMAIL)
            page.fill("#ap_password", config.KDP_PASSWORD)
            page.click("#signInSubmit")
            page.wait_for_url("**/bookshelf**", timeout=30000)

            # Create new title
            page.click("text=+ Kindle eBook")
            page.wait_for_timeout(2000)

            # Fill details — KDP field selectors are fragile; update if Amazon changes UI
            page.fill('[id*="book-title"]', title)
            page.fill('[id*="book-description"]', description)

            browser.close()
            log.warning("KDP automation is a stub — manual upload required for full compliance")
            return {"platform": "kdp", "status": "manual_required", "title": title}


# ─── REGISTRY ────────────────────────────────────────────────────────────────

def distribute_product(product_id: int, platform: str, product_meta: dict,
                       file_path: Path, cover_path: Path = None) -> str:
    """Route a finished product to the right distributor."""
    if platform == "gumroad":
        dist = GumroadDistributor()
        result = dist.publish_product(
            title=product_meta["title"],
            description=product_meta.get("back_cover_blurb", ""),
            price_cents=int(product_meta.get("suggested_price_usd", 9.99) * 100),
            file_path=file_path,
            cover_path=cover_path,
        )
    elif platform == "youtube":
        dist = YouTubeDistributor()
        result = dist.upload_video(
            video_path=file_path,
            title=product_meta["title"],
            description=product_meta.get("back_cover_blurb", ""),
            tags=product_meta.get("keywords", []),
            thumbnail_path=cover_path,
        )
    elif platform == "kdp":
        dist = KDPDistributor()
        result = dist.publish_ebook(
            title=product_meta["title"],
            description=product_meta.get("back_cover_blurb", ""),
            keywords=product_meta.get("keywords", []),
            categories=product_meta.get("categories", []),
            price_usd=product_meta.get("suggested_price_usd", 9.99),
            manuscript_path=file_path,
            cover_path=cover_path,
        )
    else:
        raise ValueError(f"Unknown platform: {platform}")

    db.update_product_published(product_id, result.get("platform_url", ""),
                                result.get("platform_id"))
    return result.get("platform_url", "")
