import json

from bookpipeline.parsers import (find_list_price, normalize_isbn, normalize_publisher, parse_product)


def page(ld=None, body=""):
    ld_tag = f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>' if ld else ""
    return f"<html><head><title>x</title>{ld_tag}</head><body>{body}</body></html>"


def test_isbn_validation():
    assert normalize_isbn("978-616-04-5156-?") is None
    assert normalize_isbn("9786160845156") == "9786160845156"
    assert normalize_isbn("978-616-08-4515-6") == "9786160845156"
    assert normalize_isbn("8859161005681") is None           # บาร์โค้ดที่ไม่ใช่ ISBN
    assert normalize_isbn("9786160845157") is None           # check digit ผิด
    assert normalize_isbn("616487047X") == "9786164870475"   # ISBN-10 -> 13


def test_publisher_normalization():
    assert normalize_publisher("ซีเอ็ดยูเคชั่น/se-ed") == "ซีเอ็ดยูเคชั่น"
    assert normalize_publisher("ซีเอ็ดยูเคชั่น, บมจ. ") == "ซีเอ็ดยูเคชั่น"
    assert normalize_publisher(None) is None


def test_list_price_pairs():
    assert find_list_price("฿289 ฿340", 289) == 340      # B2S: ราคาขาย แล้วราคาปก
    assert find_list_price("ราคาปกติ ฿ 365 -10% ฿ 328.5", 328.5) == 365   # Se-ed: ราคาปกติก่อน
    assert find_list_price("280.25 บาท 295.00 บาท", 280.25) == 295.0     # Naiin
    assert find_list_price("฿100", 100) is None


def test_b2s_style_page():
    html = page(
        {"@type": "Product", "name": "หนังสือ การเขียนโปรเเกรมด้วย Python ฉบับพื้นฐาน", "sku": "DA01540",
         "offers": {"availability": "http://schema.org/InStock", "price": "289.00", "priceCurrency": "THB"}},
        "<div>-15% ฿289 ฿340</div><div>ข้อมูลสินค้า ISBN 9786160845156 ชื่อศิลปิน/ ชื่อ ผู้แต่ง / ค่าย บัญชา</div>"
        "<div>ชื่อสำนักพิมพ์ ซีเอ็ดยูเคชั่น, บมจ. </div><div>ขนาด 19x24x4.7</div>",
    )
    r = parse_product(html, "https://www.b2s.co.th/5385487.html", "b2s")
    assert r["isbn_raw"] == "9786160845156"       # sku ภายในไม่ใช่ ISBN -> ใช้ป้าย ISBN
    assert r["price"] == 289.0 and r["list_price"] == 340.0 and r["in_stock"] is True
    assert r["publisher"] == "ซีเอ็ดยูเคชั่น"
    assert r["title"].startswith("การเขียนโปรเเกรม")


def test_seed_style_page_sku_is_isbn():
    html = page({"name": "คู่มือเขียนโปรแกรมด้วย Python", "sku": "9786162048128",
                 "offers": {"priceCurrency": "THB", "price": "265.50", "lowPrice": "265.50", "highPrice": "265.50"}},
                "<p>ราคาปกติ ฿ 295 -10% ฿ 265.5</p>")
    r = parse_product(html, "https://www.se-ed.com/physical/x", "seed")
    assert r["isbn_raw"] == "9786162048128" and r["price"] == 265.5 and r["list_price"] == 295.0
    assert r["_is_physical"] is True


def test_naiin_ebook_is_rejected_and_print_is_kept():
    ebook = ("<html><head><title>การเขียนโปรเเกรมด้วย Python ฉบับพื้นฐาน E-Books</title></head><body>"
             "<div>บาร์โค้ด</div><div>9786160845170</div><div>ประเภทไฟล์</div><div>PDF</div></body></html>")
    assert parse_product(ebook, "https://www.naiin.com/product/detail/556168", "naiin")["_is_physical"] is False
    printed = page({"name": "การสร้างโค้ดด้วย AI สำหรับภาษา Python", "offers": [{"price": 280.25}]},
                   "<div>บาร์โค้ด</div><div>9786160845170</div>")
    r = parse_product(printed, "https://www.naiin.com/product/detail/665396", "naiin")
    assert r["_is_physical"] is True and r["price"] == 280.25 and r["isbn_raw"] == "9786160845170"
