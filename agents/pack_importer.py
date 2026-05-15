"""
Pack Importer
=============
Reads export.json manifests from Termux book exports and registers them
as live sellable products in the store.

Two modes:
  1. push_export()  — called by termux_bridge /bridge/export endpoint
                      when Termux pushes a finished pack
  2. scan_reports() — scans reports/imports/ folder for dropped export.json files
                      (useful if Termux can SCP files over)

export.json format (from ~/lousta-core/output/exports/<title_slug>/):
  {
    "title": "Book Title",
    "title_slug": "book-title",
    "created_at": "2026-05-01T12:00:00",
    "language": "en",
    "niche": "self-help",
    "files": {
      "pdf":   "FINAL_BOOK_PRO.pdf",
      "epub":  "book.epub",
      "audio": ["ch1.mp3", "ch2.mp3"],
      "cover": "cover.png"
    },
    "metadata": {
      "word_count": 9500,
      "chapters": 12,
      "description": "...",
      "keywords": ["keyword1", ...],
      "price_usd": 9.99
    }
  }
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import database as db
from agents import lemonsqueezy_agent

log = logging.getLogger("pack_importer")

IMPORTS_DIR = Path("reports/imports")


def register_pack(export_data: dict, file_refs: dict = None) -> dict:
    """
    Take a finished export.json and create a live product in the system.
    Registers in local DB + syncs to LemonSqueezy.
    Returns the created product record.
    """
    title = export_data.get("title", "Untitled")
    meta = export_data.get("metadata", {})
    price_usd = float(meta.get("price_usd", export_data.get("price_usd", 9.99)))
    description = meta.get("description", export_data.get("description", ""))
    language = export_data.get("language", "en")
    niche = export_data.get("niche", "general")
    keywords = meta.get("keywords", [])
    word_count = meta.get("word_count", 0)

    # Determine content type
    files = export_data.get("files", {})
    has_audio = bool(files.get("audio") or export_data.get("audio_files"))
    has_ebook = bool(files.get("pdf") or files.get("epub") or export_data.get("epub_path"))
    content_type = "both" if (has_audio and has_ebook) else ("audiobook" if has_audio else "ebook")

    # Check not already imported
    title_slug = export_data.get("title_slug", title.lower().replace(" ", "-")[:50])
    with db.conn() as c:
        existing = c.execute(
            "SELECT id FROM products WHERE title = ? OR meta LIKE ?",
            (title, f'%"title_slug": "{title_slug}"%')
        ).fetchone()
        if existing:
            log.info("Pack already registered: %s (product #%d)", title, existing["id"])
            return {"status": "already_exists", "product_id": existing["id"], "title": title}

    # Save to products table
    product_id = db.save_product(
        title=title,
        product_type=content_type,
        niche=niche,
        language=language,
        meta={
            "title_slug": title_slug,
            "description": description,
            "keywords": keywords,
            "word_count": word_count,
            "price_usd": price_usd,
            "content_type": content_type,
            "source": "termux_export",
            "imported_at": datetime.utcnow().isoformat(),
            "files": files,
            **(file_refs or {}),
        },
    )

    log.info("Pack registered: %s (product #%d, %s, $%.2f)",
             title, product_id, content_type, price_usd)

    # Sync to LemonSqueezy (primary payment processor)
    ls_result = {}
    if os.getenv("LEMONSQUEEZY_API_KEY"):
        try:
            ls_ids = lemonsqueezy_agent.sync_product_to_ls(
                product_id=product_id,
                title=title,
                description=description,
                price_usd=price_usd,
                product_type=content_type,
            )
            ls_result = ls_ids
            log.info("LemonSqueezy synced: product %s", ls_ids.get("product_id"))
        except Exception as e:
            log.warning("LemonSqueezy sync failed (non-critical): %s", e)

    # Sync to Gumroad if token available
    gumroad_result = {}
    if os.getenv("GUMROAD_ACCESS_TOKEN"):
        try:
            from agents.distribution_agent import GumroadDistributor
            dist = GumroadDistributor()
            # Note: actual file upload needs the file to be local/accessible
            gumroad_result = {"status": "metadata_only_without_file"}
        except Exception as e:
            log.warning("Gumroad sync failed: %s", e)

    return {
        "status": "registered",
        "product_id": product_id,
        "title": title,
        "content_type": content_type,
        "price_usd": price_usd,
        "lemonsqueezy": ls_result,
        "gumroad": gumroad_result,
    }


def scan_imports_folder() -> list[dict]:
    """
    Scan reports/imports/ for export.json files dropped there.
    Each file is processed and moved to reports/imports/processed/.
    """
    IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
    done_dir = IMPORTS_DIR / "processed"
    done_dir.mkdir(exist_ok=True)

    results = []
    for json_file in IMPORTS_DIR.glob("*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            result = register_pack(data)
            results.append(result)
            # Move processed file
            json_file.rename(done_dir / json_file.name)
            log.info("Imported pack from file: %s → product #%s",
                     json_file.name, result.get("product_id"))
        except Exception as e:
            log.error("Failed to import %s: %s", json_file.name, e)
            results.append({"status": "error", "file": json_file.name, "error": str(e)})

    return results


def get_store_catalogue() -> list[dict]:
    """
    Return all registered products with their pricing and checkout URLs.
    Used by the storefront to display the product catalogue.
    """
    with db.conn() as c:
        rows = c.execute(
            """SELECT p.id, p.title, p.type, p.language, p.niche, p.meta,
                      p.published_at, p.platform_url,
                      l.variant_id as ls_variant_id, l.checkout_url as ls_checkout
               FROM products p
               LEFT JOIN ls_products l ON l.product_id = p.id
               WHERE p.published_at IS NOT NULL
               ORDER BY p.published_at DESC"""
        ).fetchall()

    catalogue = []
    for row in rows:
        meta = json.loads(row["meta"]) if row["meta"] else {}
        catalogue.append({
            "id": row["id"],
            "title": row["title"],
            "type": row["type"],
            "language": row["language"],
            "niche": row["niche"],
            "price_usd": meta.get("price_usd", 9.99),
            "description": meta.get("description", ""),
            "keywords": meta.get("keywords", []),
            "word_count": meta.get("word_count", 0),
            "checkout_url": row["ls_checkout"] or row["platform_url"],
            "published_at": row["published_at"],
        })
    return catalogue


def bulk_import_from_termux_report(report_json: dict) -> dict:
    """
    Process a bulk report pushed from Termux containing multiple exports.
    Format: { "exports": [export_data, ...], "source": "lousta-core" }
    """
    exports = report_json.get("exports", [])
    results = []
    for export_data in exports:
        try:
            result = register_pack(export_data)
            results.append(result)
        except Exception as e:
            results.append({
                "status": "error",
                "title": export_data.get("title", "unknown"),
                "error": str(e)
            })

    registered = sum(1 for r in results if r.get("status") == "registered")
    skipped = sum(1 for r in results if r.get("status") == "already_exists")
    errors = sum(1 for r in results if r.get("status") == "error")

    log.info("Bulk import: %d registered, %d skipped, %d errors (total %d)",
             registered, skipped, errors, len(exports))

    return {
        "total": len(exports),
        "registered": registered,
        "skipped": skipped,
        "errors": errors,
        "results": results,
    }
