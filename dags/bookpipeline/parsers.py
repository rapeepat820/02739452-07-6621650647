"""แปลง HTML หน้าสินค้า -> dict ข้อมูลหนังสือ (ไม่มี I/O จึงเทสต์ง่าย)"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

# ISBN / บาร์โค้ด: เลขที่ตามหลังป้าย เช่น "ISBN : 978-616-04-6740-2", "บาร์โค้ด 9786160842209"
LABELLED_CODE_RE = re.compile(r"(?:ISBN|บาร์โค้ด|Barcode)\s*[:：]?\s*([0-9][0-9\-]{8,15}[0-9Xx])", re.I)
AMOUNT_RE = re.compile(r"(?:฿\s*(\d[\d,]*(?:\.\d+)?))|(?:(\d[\d,]*(?:\.\d+)?)\s*บาท)")


# ---------- ISBN ----------
def isbn13_checksum_ok(d: str) -> bool:
    if len(d) != 13 or not d.isdigit() or d[:3] not in ("978", "979"):
        return False
    s = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(d[:12]))
    return (10 - s % 10) % 10 == int(d[12])


def normalize_isbn(raw) -> str | None:
    """คืน ISBN-13 (ตัวเลขล้วน) ถ้าถูกต้อง ไม่เช่นนั้นคืน None (รองรับ ISBN-10 โดยแปลงเป็น 13)"""
    if not raw:
        return None
    d = re.sub(r"[^0-9Xx]", "", str(raw)).upper()
    if len(d) == 10 and d[:9].isdigit():
        core = "978" + d[:9]
        s = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(core))
        d = core + str((10 - s % 10) % 10)
    return d if isbn13_checksum_ok(d) else None


# ---------- ตัวช่วยเล็กๆ ----------
def to_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("฿", "").strip())
    except ValueError:
        return None


def normalize_publisher(p: str | None) -> str | None:
    if not p:
        return None
    p = p.split("/")[0]
    for junk in ("(มหาชน)", "บมจ.", "บจก.", "บริษัท", "จำกัด", "จก."):
        p = p.replace(junk, "")
    p = re.sub(r"[,\s]+", " ", p).strip(" ,.")
    return p or None


def _jsonld_blocks(soup: BeautifulSoup) -> list[dict]:
    out = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except (ValueError, TypeError):
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                out.append(item)
                graph = item.get("@graph")
                if isinstance(graph, list):
                    stack.extend(graph)
    return out


def _find_product(blocks: list[dict]) -> dict | None:
    for b in blocks:
        t = b.get("@type")
        types = t if isinstance(t, list) else [t]
        if "Product" in types or "Book" in types:
            return b
    for b in blocks:  # บางร้านใส่แค่ offers+sku โดยไม่มี @type
        if b.get("offers") or b.get("sku"):
            return b
    return None


def _offer_fields(product: dict) -> tuple[float | None, float | None, bool | None]:
    offers = product.get("offers")
    if isinstance(offers, list):
        offers = offers[0] if offers else None
    if not isinstance(offers, dict):
        return None, None, None
    price = to_float(offers.get("price")) or to_float(offers.get("lowPrice"))
    high = to_float(offers.get("highPrice"))
    avail = str(offers.get("availability") or "")
    in_stock = True if avail.endswith("InStock") else False if avail.endswith(("OutOfStock", "SoldOut")) else None
    return price, high, in_stock


def find_list_price(text: str, price: float | None) -> float | None:
    """หาราคาปกติ: จำนวนเงินสองค่าติดกันในหน้า โดยค่าหนึ่งเท่าราคาขาย อีกค่ามากกว่า"""
    if price is None:
        return None
    amounts = [to_float(a or b) for a, b in AMOUNT_RE.findall(text)]
    amounts = [a for a in amounts if a is not None]
    for x, y in zip(amounts, amounts[1:]):
        if abs(x - price) < 0.011 and y > price:
            return y
        if abs(y - price) < 0.011 and x > price:
            return x
    return None


def _publisher(text: str) -> str | None:
    for pat in (
        r"ชื่อสำนักพิมพ์\s+([^\n]+?)\s*(?:ขนาด|\n|$)",
        r"สำนักพิมพ์\s*[:：]\s*([^\n]+)",
        r"สำนักพิมพ์\s*\n\s*([^\n]+)",
    ):
        m = re.search(pat, text)
        if m:
            return normalize_publisher(m.group(1))
    return None


# ---------- ตัวกรอง ----------
def is_physical(source: str, url: str, soup: BeautifulSoup, text: str) -> bool:
    """เก็บเฉพาะหนังสือเล่ม เพราะ e-book มี ISBN คนละเลขกับฉบับพิมพ์ ทำให้จับคู่ข้ามร้านไม่ได้"""
    if source == "seed":
        return "/physical/" in url
    if source == "naiin":
        title_tag = soup.title.get_text() if soup.title else ""
        if re.search(r"E-?Books?", title_tag, re.I) or "ประเภทไฟล์" in text:
            return False
    return True


def in_scope(title: str, keywords: list[str]) -> bool:
    """คำภาษาอังกฤษต้องตรงทั้งคำ (ai ไม่ตรงกับ thai) ส่วนคำภาษาไทยตรวจแบบมีอยู่ในข้อความ"""
    t = (title or "").lower()
    for k in keywords:
        if k.isascii():
            if re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", t):
                return True
        elif k in t:
            return True
    return False


# ---------- ฟังก์ชันหลัก ----------
def parse_product(html: str, url: str, source: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n", strip=True)

    product = _find_product(_jsonld_blocks(soup)) or {}
    price, high, in_stock = _offer_fields(product)

    title = product.get("name")
    if not title:
        og = soup.find("meta", property="og:title")
        title = og.get("content") if og and og.get("content") else None
    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(" ", strip=True) if h1 else None
    if title:
        title = re.sub(r"^หนังสือ\s+", "", title.strip())

    sku = str(product.get("sku") or "")
    isbn_raw = sku if normalize_isbn(sku) else None
    if not isbn_raw:
        m = LABELLED_CODE_RE.search(text)
        isbn_raw = m.group(1) if m else (sku or None)

    if price is None:  # JSON-LD ไม่มี: ใช้จำนวนเงินแรกที่พบ (ถือว่าเสี่ยง จึงบันทึกเป็น issue ตอน transform ไม่ได้ ต้องสังเกตเอง)
        amounts = [to_float(a or b) for a, b in AMOUNT_RE.findall(text)]
        price = next((a for a in amounts if a), None)

    if not title and not isbn_raw:
        return None

    list_price = high if (high and price and high > price) else find_list_price(text, price)

    return {
        "source": source,
        "url": url,
        "title": title,
        "isbn_raw": isbn_raw,
        "price": price,
        "list_price": list_price,
        "in_stock": in_stock,
        "publisher": _publisher(text),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "_is_physical": is_physical(source, url, soup, text),
    }
