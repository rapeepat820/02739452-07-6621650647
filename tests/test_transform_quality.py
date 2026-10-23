from bookpipeline.quality import evaluate
from bookpipeline.transform import transform_rows


def raw(**kw):
    base = {"source": "b2s", "url": "https://x/1", "title": "Python", "isbn_raw": "9786160845156",
            "price": 289.0, "list_price": 340.0, "in_stock": True, "publisher": "ซีเอ็ดยูเคชั่น/se-ed",
            "scraped_at": "2026-10-23T00:00:00+00:00"}
    base.update(kw)
    return base


def test_transform_flags_and_dedupes():
    rows = transform_rows([
        raw(),
        raw(url="https://x/dup"),                                   # ISBN ซ้ำในแหล่งเดียวกัน -> เหลือ 1
        raw(url="https://x/2", isbn_raw="8859161005681"),           # ISBN เสีย
        raw(url="https://x/3", isbn_raw="9786162048128", price=None),
        raw(url="https://x/4", isbn_raw="9786164870475", list_price=100.0),  # ปกต่ำกว่าราคาขาย -> ทิ้ง list_price
    ])
    by_url = {r["url"]: r for r in rows}
    assert len(rows) == 4
    assert by_url["https://x/2"]["issues"] == "invalid_isbn"
    assert by_url["https://x/3"]["issues"] == "invalid_price"
    assert by_url["https://x/4"]["list_price"] is None
    assert "https://x/dup" not in by_url
    assert by_url["https://x/1"]["publisher"] == "ซีเอ็ดยูเคชั่น"


def test_quality_gate():
    good = [{"issues": None}] * 90 + [{"issues": "invalid_isbn"}] * 5
    assert evaluate(good, 0.25, 20)["passed"]
    bad = [{"issues": None}] * 10 + [{"issues": "invalid_price"}] * 30
    r = evaluate(bad, 0.25, 20)
    assert not r["passed"] and r["reasons"]
    assert not evaluate([{"issues": None}] * 5, 0.25, 20)["passed"]   # น้อยกว่าขั้นต่ำ
    assert not evaluate([], 0.25, 0)["passed"]
