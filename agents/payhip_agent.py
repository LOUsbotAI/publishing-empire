"""
Payhip Agent
============
Sells digital downloads directly. No API key needed for basic uploads —
uses Playwright automation. Payhip pays via PayPal or bank transfer weekly.

Products land on: payhip.com/YOUR_STORE
Payout: weekly to PayPal → your bank (or direct bank in supported countries).
"""
import logging
import os
import time
from pathlib import Path

log = logging.getLogger("payhip")

PAYHIP_EMAIL    = os.getenv("PAYHIP_EMAIL", "")
PAYHIP_PASSWORD = os.getenv("PAYHIP_PASSWORD", "")
PAYHIP_BASE_URL = "https://payhip.com"


def _browser():
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    return p, browser


def upload_product(
    file_path: Path,
    title: str,
    description: str = "",
    price_usd: float = 4.99,
    cover_path: Path = None,
    tags: list[str] = None,
    category: str = "ebooks",
) -> dict:
    """
    Upload an ebook or audio file to Payhip.
    Returns dict with product link and status.
    """
    if not PAYHIP_EMAIL or not PAYHIP_PASSWORD:
        log.warning("PAYHIP_EMAIL/PASSWORD not set — skipping Payhip")
        return {"status": "skipped", "reason": "credentials_missing"}

    if not file_path.exists():
        return {"status": "error", "reason": f"File not found: {file_path}"}

    p, browser = _browser()
    result = {}

    try:
        page = browser.new_page()
        page.set_default_timeout(60000)

        # ── Login ──────────────────────────────────────────────────────────
        page.goto(f"{PAYHIP_BASE_URL}/login")
        page.fill("input[name='email']", PAYHIP_EMAIL)
        page.fill("input[name='password']", PAYHIP_PASSWORD)
        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_load_state("networkidle")
        log.info("Payhip login successful")

        # ── Add product ────────────────────────────────────────────────────
        page.goto(f"{PAYHIP_BASE_URL}/products/new")
        page.wait_for_load_state("networkidle")

        # Product type — digital download
        dl_option = page.locator("a[href*='digital'], button:has-text('Digital Download')")
        if dl_option.count() > 0:
            dl_option.first.click()
            page.wait_for_load_state("networkidle")

        # Title
        page.fill("input[name='title'], input[placeholder*='title' i]", title)

        # Price
        price_input = page.locator("input[name='price'], input[placeholder*='price' i]")
        if price_input.count() > 0:
            price_input.fill(str(price_usd))

        # Description
        if description:
            desc = page.locator("textarea[name='description'], div[contenteditable='true']")
            if desc.count() > 0:
                desc.first.fill(description[:2000])

        # Cover image
        if cover_path and cover_path.exists():
            cover_input = page.locator("input[type='file'][accept*='image']")
            if cover_input.count() > 0:
                cover_input.set_input_files(str(cover_path))
                time.sleep(2)

        # Product file
        file_input = page.locator("input[type='file']:not([accept*='image'])")
        if file_input.count() == 0:
            file_input = page.locator("input[type='file']")
        if file_input.count() > 0:
            file_input.first.set_input_files(str(file_path))
            page.wait_for_load_state("networkidle")
            time.sleep(3)

        # Tags
        if tags:
            tag_input = page.locator("input[name='tags'], input[placeholder*='tag' i]")
            if tag_input.count() > 0:
                tag_input.fill(", ".join(tags[:5]))

        # Publish
        page.click("button[type='submit']:has-text('Publish'), button:has-text('Save'), button:has-text('Add')")
        page.wait_for_load_state("networkidle")

        product_url = page.url
        result = {
            "status": "published",
            "platform": "payhip",
            "title": title,
            "url": product_url,
            "price_usd": price_usd,
        }
        log.info("Payhip product published: %s → %s", title, product_url)

    except Exception as e:
        log.error("Payhip upload failed for '%s': %s", title, e)
        result = {"status": "error", "platform": "payhip", "error": str(e)}
    finally:
        browser.close()
        p.stop()

    return result
