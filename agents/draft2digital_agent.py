"""
Draft2Digital Agent
===================
Distributes to: Apple Books, Barnes & Noble, Kobo, Scribd,
                OverDrive/libraries, Tolino, Vivlio, and 40+ more.

D2D has no public upload API — this uses Playwright browser automation
(same approach as KDP). Set D2D_EMAIL + D2D_PASSWORD in .env.

Payout: D2D pays monthly via Payoneer/PayPal to your bank.
"""
import logging
import os
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger("draft2digital")

D2D_EMAIL    = os.getenv("D2D_EMAIL", "")
D2D_PASSWORD = os.getenv("D2D_PASSWORD", "")
D2D_BASE_URL = "https://www.draft2digital.com"


def _browser():
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"]
    )
    return p, browser


def upload_ebook(
    epub_path: Path,
    title: str,
    author: str = "Lousta Corp",
    description: str = "",
    keywords: list[str] = None,
    price_usd: float = 4.99,
    bisac_category: str = "SEL027000",  # SELF-HELP / Personal Growth / Success
    language: str = "en",
) -> dict:
    """
    Upload an EPUB to Draft2Digital and publish to all partner retailers.
    Returns dict with D2D book ID and status.
    """
    if not D2D_EMAIL or not D2D_PASSWORD:
        log.warning("D2D_EMAIL or D2D_PASSWORD not set — skipping D2D upload")
        return {"status": "skipped", "reason": "credentials_missing"}

    if not epub_path.exists():
        return {"status": "error", "reason": f"EPUB not found: {epub_path}"}

    log.info("Starting D2D upload: %s", title)
    p, browser = _browser()
    result = {}

    try:
        page = browser.new_page()
        page.set_default_timeout(60000)

        # ── Login ──────────────────────────────────────────────────────────
        page.goto(f"{D2D_BASE_URL}/login")
        page.fill("input[name='email']", D2D_EMAIL)
        page.fill("input[name='password']", D2D_PASSWORD)
        page.click("button[type='submit']")
        page.wait_for_url("**/book/list**", timeout=30000)
        log.info("D2D login successful")

        # ── Create new book ────────────────────────────────────────────────
        page.click("a[href*='/book/create'], a:has-text('New Book'), button:has-text('Add Book')")
        page.wait_for_load_state("networkidle")

        # Title & author
        page.fill("input[name='title'], input[placeholder*='title' i]", title)
        page.fill("input[name='author'], input[placeholder*='author' i]", author)

        # Description
        if description:
            desc_sel = "textarea[name='description'], textarea[placeholder*='description' i]"
            if page.locator(desc_sel).count() > 0:
                page.fill(desc_sel, description[:3000])

        # Keywords
        if keywords:
            kw_input = page.locator("input[name='keywords'], input[placeholder*='keyword' i]")
            if kw_input.count() > 0:
                kw_input.fill(", ".join(keywords[:7]))

        # Language
        lang_sel = page.locator("select[name='language']")
        if lang_sel.count() > 0:
            lang_sel.select_option(value=language)

        # Price
        price_input = page.locator("input[name='price'], input[placeholder*='price' i]")
        if price_input.count() > 0:
            price_input.fill(str(price_usd))

        # Upload EPUB
        file_input = page.locator("input[type='file']")
        if file_input.count() > 0:
            file_input.set_input_files(str(epub_path))
            page.wait_for_load_state("networkidle")
            time.sleep(3)

        # Save / continue
        page.click("button[type='submit'], button:has-text('Save'), button:has-text('Continue')")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # ── Select all retail channels ─────────────────────────────────────
        # Check all distributor checkboxes
        checkboxes = page.locator("input[type='checkbox'][name*='channel'], input[type='checkbox'][name*='retailer']")
        count = checkboxes.count()
        for i in range(count):
            cb = checkboxes.nth(i)
            if not cb.is_checked():
                cb.check()
        log.info("Selected %d distribution channels", count)

        # Final publish
        publish_btn = page.locator("button:has-text('Publish'), button:has-text('Submit')")
        if publish_btn.count() > 0:
            publish_btn.first.click()
            page.wait_for_load_state("networkidle")

        # Extract D2D book ID from URL
        book_id = page.url.split("/")[-1].split("?")[0]
        result = {
            "status": "published",
            "platform": "draft2digital",
            "book_id": book_id,
            "title": title,
            "channels": count,
            "url": page.url,
        }
        log.info("D2D published: %s (ID: %s, %d channels)", title, book_id, count)

    except Exception as e:
        log.error("D2D upload failed for '%s': %s", title, e)
        result = {"status": "error", "platform": "draft2digital", "error": str(e)}
    finally:
        browser.close()
        p.stop()

    return result


def get_sales_report() -> list[dict]:
    """
    Scrape current month sales data from D2D dashboard.
    Returns list of sale records.
    """
    if not D2D_EMAIL or not D2D_PASSWORD:
        return []

    p, browser = _browser()
    sales = []
    try:
        page = browser.new_page()
        page.set_default_timeout(30000)

        page.goto(f"{D2D_BASE_URL}/login")
        page.fill("input[name='email']", D2D_EMAIL)
        page.fill("input[name='password']", D2D_PASSWORD)
        page.click("button[type='submit']")
        page.wait_for_url("**/book/list**", timeout=20000)

        page.goto(f"{D2D_BASE_URL}/report/sales")
        page.wait_for_load_state("networkidle")

        rows = page.locator("table tbody tr")
        for i in range(rows.count()):
            cells = rows.nth(i).locator("td")
            if cells.count() >= 3:
                sales.append({
                    "title": cells.nth(0).text_content().strip(),
                    "retailer": cells.nth(1).text_content().strip(),
                    "units": cells.nth(2).text_content().strip(),
                    "royalty": cells.nth(3).text_content().strip() if cells.count() > 3 else "0",
                })

        log.info("D2D: scraped %d sales records", len(sales))
    except Exception as e:
        log.error("D2D sales report failed: %s", e)
    finally:
        browser.close()
        p.stop()

    return sales
