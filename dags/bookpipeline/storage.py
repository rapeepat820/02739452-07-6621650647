"""การอ่าน/เขียน PostgreSQL ทั้งหมดของ pipeline"""
from __future__ import annotations

import os
from pathlib import Path

import psycopg2
import psycopg2.extras

SCHEMA_FILE = Path(__file__).with_name("schema.sql")

STAGING_COLS = ["run_id", "source", "isbn_raw", "isbn", "title", "publisher", "price",
                "list_price", "in_stock", "url", "scraped_at", "issues"]


def get_conn():
    return psycopg2.connect(os.environ["DATA_DB_DSN"])


def ensure_schema() -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(SCHEMA_FILE.read_text(encoding="utf-8"))


def start_run(run_id: str) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO pipeline_runs (run_id, status) VALUES (%s, 'running')
               ON CONFLICT (run_id) DO UPDATE SET started_at = now(), finished_at = NULL, status = 'running'""",
            (run_id,),
        )


def update_run(run_id: str, **fields) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k} = %s" for k in fields)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"UPDATE pipeline_runs SET {sets} WHERE run_id = %s", [*fields.values(), run_id])


def stage_rows(run_id: str, rows: list[dict]) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM staging_prices WHERE run_id = %s", (run_id,))
        values = [(run_id, r["source"], r.get("isbn_raw"), r.get("isbn"), r.get("title"), r.get("publisher"),
                   r.get("price"), r.get("list_price"), r.get("in_stock"), r.get("url"),
                   r.get("scraped_at"), r.get("issues")) for r in rows]
        psycopg2.extras.execute_values(
            cur, f"INSERT INTO staging_prices ({', '.join(STAGING_COLS)}) VALUES %s", values)


def fetch_staging(run_id: str) -> list[dict]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM staging_prices WHERE run_id = %s", (run_id,))
        return [dict(r) for r in cur.fetchall()]


def upsert_prices(rows: list[dict]) -> int:
    """UPSERT ด้วย (isbn, source): รันซ้ำกี่ครั้งจำนวนแถวก็ไม่เพิ่ม"""
    dedup = {(r["isbn"], r["source"]): r for r in rows}
    if not dedup:
        return 0
    values = [(r["isbn"], r["source"], r["title"], r.get("publisher"), r["price"], r.get("list_price"),
               r.get("in_stock"), r["url"], r["scraped_at"]) for r in dedup.values()]
    with get_conn() as conn, conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """INSERT INTO book_prices (isbn, source, title, publisher, price, list_price, in_stock, url, scraped_at)
               VALUES %s
               ON CONFLICT (isbn, source) DO UPDATE SET
                   title = EXCLUDED.title, publisher = EXCLUDED.publisher, price = EXCLUDED.price,
                   list_price = EXCLUDED.list_price, in_stock = EXCLUDED.in_stock, url = EXCLUDED.url,
                   scraped_at = EXCLUDED.scraped_at, updated_at = now()""",
            values,
        )
    return len(values)


def insert_rejected(run_id: str, rows: list[dict], reason: str | None = None) -> int:
    if not rows:
        return 0
    values = [(run_id, r.get("source"), r.get("isbn_raw"), r.get("title"), r.get("price"), r.get("url"),
               reason or r.get("issues")) for r in rows]
    with get_conn() as conn, conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur, "INSERT INTO rejected_rows (run_id, source, isbn_raw, title, price, url, reason) VALUES %s", values)
    return len(values)


def rebuild_books_unique() -> int:
    """ตัดรายการซ้ำข้ามแหล่งด้วย ISBN: 1 ISBN = 1 แถว พร้อมราคาต่ำสุดและร้านที่ถูกที่สุด"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO books_unique (isbn, title, publisher, n_sources, min_price, max_price,
                                         price_spread, cheapest_source, updated_at)
               SELECT isbn,
                      (array_agg(title ORDER BY length(title) DESC, source))[1],
                      (array_agg(publisher ORDER BY (publisher IS NULL), source))[1],
                      count(*), min(price), max(price), max(price) - min(price),
                      (array_agg(source ORDER BY price, source))[1], now()
               FROM book_prices GROUP BY isbn
               ON CONFLICT (isbn) DO UPDATE SET
                   title = EXCLUDED.title, publisher = EXCLUDED.publisher, n_sources = EXCLUDED.n_sources,
                   min_price = EXCLUDED.min_price, max_price = EXCLUDED.max_price,
                   price_spread = EXCLUDED.price_spread, cheapest_source = EXCLUDED.cheapest_source,
                   updated_at = now()""")
        cur.execute("DELETE FROM books_unique WHERE isbn NOT IN (SELECT isbn FROM book_prices)")
        cur.execute("SELECT count(*) FROM books_unique")
        return cur.fetchone()[0]


def drop_staging(run_id: str) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM staging_prices WHERE run_id = %s", (run_id,))
