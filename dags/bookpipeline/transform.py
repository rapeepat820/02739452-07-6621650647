"""ทำความสะอาดข้อมูลดิบของแต่ละแหล่งให้เป็น schema เดียวกัน (ไม่มี I/O)"""
from __future__ import annotations

from .parsers import normalize_isbn, normalize_publisher

MAX_PLAUSIBLE_PRICE = 50000.0


def transform_rows(rows: list[dict]) -> list[dict]:
    out: dict[tuple, dict] = {}
    for r in rows:
        issues: list[str] = []
        isbn = normalize_isbn(r.get("isbn_raw"))
        if not isbn:
            issues.append("invalid_isbn")
        title = (r.get("title") or "").strip()
        if not title:
            issues.append("missing_title")
        price = r.get("price")
        if price is None or price <= 0 or price > MAX_PLAUSIBLE_PRICE:
            issues.append("invalid_price")
        list_price = r.get("list_price")
        if list_price is not None and (price is None or list_price < price):
            list_price = None

        rec = {
            "source": r["source"],
            "url": r["url"],
            "isbn_raw": r.get("isbn_raw"),
            "isbn": isbn,
            "title": title or None,
            "publisher": normalize_publisher(r.get("publisher")),
            "price": price,
            "list_price": list_price,
            "in_stock": r.get("in_stock"),
            "scraped_at": r.get("scraped_at"),
            "issues": ";".join(issues) or None,
        }
        # ตัดซ้ำภายในแหล่งเดียวกันด้วย ISBN (ถ้า ISBN เสีย ใช้ URL เป็นคีย์แทน)
        key = (r["source"], isbn or r["url"])
        if key not in out or (out[key]["issues"] and not rec["issues"]):
            out[key] = rec
    return list(out.values())
