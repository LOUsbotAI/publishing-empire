import sqlite3
import json
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "empire.db"


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            pipeline    TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'pending',
            title       TEXT,
            niche       TEXT,
            language    TEXT DEFAULT 'en',
            meta        TEXT DEFAULT '{}',
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS products (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id          INTEGER REFERENCES jobs(id),
            title           TEXT NOT NULL,
            type            TEXT NOT NULL,
            language        TEXT DEFAULT 'en',
            file_path       TEXT,
            platform        TEXT,
            platform_id     TEXT,
            platform_url    TEXT,
            price_usd       REAL,
            published_at    TEXT,
            revenue_usd     REAL DEFAULT 0,
            units_sold      INTEGER DEFAULT 0,
            meta            TEXT DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS revenue_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id  INTEGER REFERENCES products(id),
            source      TEXT,
            amount_usd  REAL,
            currency    TEXT DEFAULT 'USD',
            recorded_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS social_posts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id  INTEGER REFERENCES products(id),
            platform    TEXT,
            content     TEXT,
            media_path  TEXT,
            post_id     TEXT,
            posted_at   TEXT,
            impressions INTEGER DEFAULT 0,
            clicks      INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS stripe_products (
            product_id          INTEGER PRIMARY KEY REFERENCES products(id),
            stripe_product_id   TEXT NOT NULL,
            stripe_price_id     TEXT NOT NULL,
            price_usd           REAL,
            active              INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS download_tokens (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            token           TEXT UNIQUE NOT NULL,
            product_id      INTEGER REFERENCES products(id),
            customer_email  TEXT,
            expires_at      TEXT NOT NULL,
            used            INTEGER DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS orders (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            stripe_session_id   TEXT UNIQUE,
            product_id          INTEGER REFERENCES products(id),
            customer_email      TEXT,
            amount_usd          REAL,
            status              TEXT DEFAULT 'pending',
            download_token      TEXT,
            created_at          TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS payout_log (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            stripe_payout_id    TEXT UNIQUE,
            amount_usd          REAL,
            currency            TEXT DEFAULT 'usd',
            status              TEXT,
            initiated_at        TEXT,
            eta                 TEXT
        );

        CREATE TABLE IF NOT EXISTS ls_products (
            product_id      INTEGER PRIMARY KEY REFERENCES products(id),
            ls_product_id   TEXT NOT NULL,
            ls_variant_id   TEXT NOT NULL,
            price_usd       REAL,
            active          INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS email_sequences (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            brief_title TEXT,
            send_day    INTEGER,
            subject     TEXT,
            html_body   TEXT,
            sent        INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS platform_sales (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            platform            TEXT NOT NULL,
            platform_sale_id    TEXT UNIQUE,
            amount_usd          REAL,
            currency            TEXT DEFAULT 'USD',
            product_name        TEXT,
            customer_email      TEXT,
            sale_date           TEXT,
            notes               TEXT,
            recorded_at         TEXT DEFAULT (datetime('now'))
        );
        """)


def update_job_by_product(product_id: int, status: str):
    with conn() as c:
        c.execute(
            """UPDATE jobs SET status=?, updated_at=datetime('now')
               WHERE id=(SELECT job_id FROM products WHERE id=?)""",
            (status, product_id)
        )


def create_job(pipeline: str, niche: str, language: str = "en", meta: dict = None) -> int:
    with conn() as c:
        cur = c.execute(
            "INSERT INTO jobs (pipeline, status, niche, language, meta) VALUES (?,?,?,?,?)",
            (pipeline, "pending", niche, language, json.dumps(meta or {}))
        )
        return cur.lastrowid


def update_job(job_id: int, status: str, title: str = None, meta: dict = None):
    with conn() as c:
        if title and meta:
            c.execute(
                "UPDATE jobs SET status=?, title=?, meta=?, updated_at=datetime('now') WHERE id=?",
                (status, title, json.dumps(meta), job_id)
            )
        elif title:
            c.execute(
                "UPDATE jobs SET status=?, title=?, updated_at=datetime('now') WHERE id=?",
                (status, title, job_id)
            )
        else:
            c.execute(
                "UPDATE jobs SET status=?, updated_at=datetime('now') WHERE id=?",
                (status, job_id)
            )


def save_product(job_id: int, title: str, product_type: str, language: str,
                 file_path: str = None, platform: str = None, price_usd: float = None,
                 meta: dict = None) -> int:
    with conn() as c:
        cur = c.execute(
            """INSERT INTO products (job_id, title, type, language, file_path, platform, price_usd, meta)
               VALUES (?,?,?,?,?,?,?,?)""",
            (job_id, title, product_type, language, file_path, platform, price_usd,
             json.dumps(meta or {}))
        )
        return cur.lastrowid


def update_product_published(product_id: int, platform_url: str, platform_id: str = None):
    with conn() as c:
        c.execute(
            """UPDATE products SET platform_url=?, platform_id=?, published_at=datetime('now')
               WHERE id=?""",
            (platform_url, platform_id, product_id)
        )


def record_revenue(product_id: int, source: str, amount_usd: float, currency: str = "USD"):
    with conn() as c:
        c.execute(
            "INSERT INTO revenue_events (product_id, source, amount_usd, currency) VALUES (?,?,?,?)",
            (product_id, source, amount_usd, currency)
        )
        c.execute(
            "UPDATE products SET revenue_usd = revenue_usd + ? WHERE id=?",
            (amount_usd, product_id)
        )


def get_pending_jobs(pipeline: str = None):
    with conn() as c:
        if pipeline:
            rows = c.execute(
                "SELECT * FROM jobs WHERE status='pending' AND pipeline=? ORDER BY created_at",
                (pipeline,)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM jobs WHERE status='pending' ORDER BY created_at"
            ).fetchall()
        return [dict(r) for r in rows]


def revenue_summary():
    with conn() as c:
        row = c.execute(
            "SELECT SUM(amount_usd) as total, COUNT(*) as events FROM revenue_events"
        ).fetchone()
        by_source = c.execute(
            "SELECT source, SUM(amount_usd) as total FROM revenue_events GROUP BY source"
        ).fetchall()
        return {
            "total_usd": row["total"] or 0,
            "events": row["events"],
            "by_source": {r["source"]: r["total"] for r in by_source}
        }
