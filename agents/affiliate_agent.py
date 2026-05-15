"""
Affiliate Agent
===============
Injects revenue-generating affiliate links into books and web pages.

Revenue sources:
  Amazon Associates    — 3-8% on book/product sales
  Skillshare          — $7-$30 per new premium member
  Udemy               — 15% on course sales
  BookBub             — author platform, reader referrals
  Audible             — $5-$15 per new member signup

Setup:
  AMAZON_ASSOCIATE_TAG = your-associate-tag-20
  SKILLSHARE_AFFILIATE_ID = your-skillshare-id
  UDEMY_AFFILIATE_ID = your-udemy-id
"""
import logging
import os
import re
from pathlib import Path
from typing import Optional

log = logging.getLogger("affiliate")

AMAZON_TAG      = os.getenv("AMAZON_ASSOCIATE_TAG", "")
SKILLSHARE_ID   = os.getenv("SKILLSHARE_AFFILIATE_ID", "")
UDEMY_ID        = os.getenv("UDEMY_AFFILIATE_ID", "")
AUDIBLE_ID      = os.getenv("AUDIBLE_AFFILIATE_ID", "")

# Category → affiliate recommendations
CATEGORY_AFFILIATES = {
    "self-help": [
        {
            "anchor": "recommended reading",
            "url": "https://www.amazon.com/s?k=self+improvement+books",
            "tag_param": "tag",
            "label": "Top Self-Improvement Books on Amazon",
            "platform": "amazon",
        },
        {
            "anchor": "online courses",
            "url": "https://www.skillshare.com/browse/productivity",
            "label": "Productivity Courses on Skillshare",
            "platform": "skillshare",
        },
    ],
    "finance": [
        {
            "anchor": "investing books",
            "url": "https://www.amazon.com/s?k=personal+finance+investing",
            "tag_param": "tag",
            "label": "Best Personal Finance Books on Amazon",
            "platform": "amazon",
        },
        {
            "anchor": "finance courses",
            "url": "https://www.udemy.com/courses/finance-and-accounting",
            "label": "Finance & Investing Courses on Udemy",
            "platform": "udemy",
        },
    ],
    "business": [
        {
            "anchor": "business books",
            "url": "https://www.amazon.com/s?k=startup+business+books",
            "tag_param": "tag",
            "label": "Top Business Books on Amazon",
            "platform": "amazon",
        },
        {
            "anchor": "business courses",
            "url": "https://www.skillshare.com/browse/business",
            "label": "Business & Entrepreneurship on Skillshare",
            "platform": "skillshare",
        },
    ],
    "health": [
        {
            "anchor": "health books",
            "url": "https://www.amazon.com/s?k=health+wellness+books",
            "tag_param": "tag",
            "label": "Best Health & Wellness Books on Amazon",
            "platform": "amazon",
        },
    ],
    "technology": [
        {
            "anchor": "programming books",
            "url": "https://www.amazon.com/s?k=python+programming+books",
            "tag_param": "tag",
            "label": "Top Programming Books on Amazon",
            "platform": "amazon",
        },
        {
            "anchor": "coding courses",
            "url": "https://www.udemy.com/courses/development",
            "label": "Programming Courses on Udemy",
            "platform": "udemy",
        },
    ],
    "general": [
        {
            "anchor": "further reading",
            "url": "https://www.amazon.com/s?k=bestseller+books",
            "tag_param": "tag",
            "label": "Bestselling Books on Amazon",
            "platform": "amazon",
        },
    ],
}


def _build_url(affiliate: dict) -> str:
    """Append the associate tag/affiliate ID to the URL."""
    url = affiliate["url"]
    platform = affiliate.get("platform", "")

    if platform == "amazon" and AMAZON_TAG:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}tag={AMAZON_TAG}"
    elif platform == "skillshare" and SKILLSHARE_ID:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}via={SKILLSHARE_ID}"
    elif platform == "udemy" and UDEMY_ID:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}couponCode={UDEMY_ID}"

    return url


def generate_affiliate_section(niche: str, title: str) -> str:
    """
    Generate a formatted "Further Resources" section with affiliate links.
    Returns HTML string suitable for injection into EPUB/PDF.
    """
    affiliates = CATEGORY_AFFILIATES.get(niche, CATEGORY_AFFILIATES["general"])

    # Always add Audible link if configured
    audible_section = ""
    if AUDIBLE_ID:
        audible_section = f"""
<li><a href="https://www.audible.com/?source_code=AUDFPWS0223189MWT-BK-ACX0-{AUDIBLE_ID}">
Listen to this book and thousands more on Audible</a></li>"""

    links_html = "\n".join([
        f'<li><a href="{_build_url(a)}">{a["label"]}</a></li>'
        for a in affiliates
    ])

    return f"""
<div class="affiliate-resources">
<h2>Further Resources</h2>
<p>To continue your journey on this topic, here are some carefully selected resources:</p>
<ul>
{links_html}
{audible_section}
</ul>
<p><em>Note: Some links above may be affiliate links. Purchasing through them
supports the author at no extra cost to you.</em></p>
</div>
"""


def inject_into_markdown(manuscript: str, niche: str, title: str) -> str:
    """
    Append an affiliate resources section to a markdown manuscript.
    Called before PDF/EPUB generation.
    """
    section = generate_affiliate_section(niche, title)
    # Convert to markdown-ish format
    md_section = "\n\n---\n\n## Further Resources\n\n"
    affiliates = CATEGORY_AFFILIATES.get(niche, CATEGORY_AFFILIATES["general"])
    for a in affiliates:
        url = _build_url(a)
        md_section += f"- [{a['label']}]({url})\n"
    if AUDIBLE_ID:
        audible_url = f"https://www.audible.com/?source_code=AUDFPWS0223189MWT-BK-ACX0-{AUDIBLE_ID}"
        md_section += f"- [Listen on Audible]({audible_url})\n"
    md_section += "\n*Some links above may be affiliate links.*\n"
    return manuscript + md_section


def inject_into_epub_html(html_content: str, niche: str, title: str) -> str:
    """
    Inject affiliate section before </body> in EPUB chapter HTML.
    """
    section = generate_affiliate_section(niche, title)
    if "</body>" in html_content:
        return html_content.replace("</body>", f"{section}</body>")
    return html_content + section


def process_book(
    manuscript_path: Path,
    niche: str,
    title: str,
    output_path: Optional[Path] = None,
) -> Path:
    """
    Read a manuscript file, inject affiliate links, write output.
    Returns path to the affiliate-enhanced manuscript.
    """
    if not manuscript_path.exists():
        log.warning("Manuscript not found: %s", manuscript_path)
        return manuscript_path

    content = manuscript_path.read_text(encoding="utf-8")

    if manuscript_path.suffix in (".md", ".txt"):
        enhanced = inject_into_markdown(content, niche, title)
    elif manuscript_path.suffix in (".html", ".htm"):
        enhanced = inject_into_epub_html(content, niche, title)
    else:
        enhanced = content  # skip unknown formats

    out_path = output_path or manuscript_path.with_suffix(f".affiliated{manuscript_path.suffix}")
    out_path.write_text(enhanced, encoding="utf-8")
    log.info("Affiliate links injected: %s → %s", manuscript_path.name, out_path.name)
    return out_path


def estimate_affiliate_revenue(books_per_month: int, avg_price: float = 9.99,
                               niche: str = "general") -> dict:
    """
    Project additional affiliate revenue on top of direct book sales.
    Conservative estimates based on typical conversion rates.
    """
    readers_per_book = 50  # estimated readers per book sold
    total_readers = books_per_month * readers_per_book

    amazon_ctr = 0.03      # 3% of readers click Amazon link
    amazon_conversion = 0.08  # 8% of clicks buy something
    amazon_aov = 25.0      # avg order value
    amazon_commission = 0.05  # 5% commission

    skillshare_ctr = 0.02
    skillshare_conversion = 0.04
    skillshare_commission = 7.0  # flat $7 per signup

    amazon_rev = total_readers * amazon_ctr * amazon_conversion * amazon_aov * amazon_commission
    skillshare_rev = total_readers * skillshare_ctr * skillshare_conversion * skillshare_commission
    total_affiliate = amazon_rev + skillshare_rev
    direct_rev = books_per_month * avg_price

    return {
        "books_per_month": books_per_month,
        "direct_book_revenue": round(direct_rev, 2),
        "amazon_affiliate_revenue": round(amazon_rev, 2),
        "skillshare_affiliate_revenue": round(skillshare_rev, 2),
        "total_affiliate_revenue": round(total_affiliate, 2),
        "total_combined": round(direct_rev + total_affiliate, 2),
        "affiliate_uplift_pct": round((total_affiliate / direct_rev * 100) if direct_rev else 0, 1),
    }
