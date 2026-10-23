"""ตรวจแหล่งข้อมูลจากเครื่องคุณเอง ก่อนรัน DAG จริง

  python scripts/probe.py robots            # เช็ก robots.txt ของทุกร้าน
  python scripts/probe.py b2s               # ลอง fetch+parse หน้า seed ของ B2S
  python scripts/probe.py naiin --crawl 15  # ลอง crawl จริงสูงสุด 15 สินค้า
ต้องติดตั้ง:  pip install -r requirements-airflow.txt
"""
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dags"))
from bookpipeline import config  # noqa: E402
from bookpipeline.parsers import normalize_isbn, parse_product  # noqa: E402
from bookpipeline.scraper import BlockedError, PoliteFetcher, crawl_source  # noqa: E402


def check_robots():
    f = PoliteFetcher(delay=0)
    for key, cfg in config.SOURCES.items():
        host = "{0.scheme}://{0.netloc}".format(urlparse(cfg["seeds"][0]))
        r = f.session.get(host + "/robots.txt", timeout=20)
        print(f"\n=== {key}: {host}/robots.txt -> HTTP {r.status_code}")
        print("\n".join(r.text.splitlines()[:40]))
        for u in cfg["seeds"]:
            print(("  อนุญาต " if f.allowed(u) else "  ห้าม    ") + u[:110])


def probe(key, crawl):
    cfg = config.SOURCES[key]
    f = PoliteFetcher()
    pat = re.compile(cfg["product_url_regex"])
    for u in cfg["seeds"]:
        print(f"\n--- {u[:110]}")
        try:
            html = f.get(u)
        except BlockedError as e:
            print("   ถูกปฏิเสธ:", e, "-> ควรเปลี่ยนแหล่ง ไม่ต้องพยายามเลี่ยง")
            continue
        if html is None:
            print("   ไม่ได้หน้า (robots ห้าม / 404)")
            continue
        if pat.match(u.split("?")[0]):
            rec = parse_product(html, u, key)
            if rec:
                rec["isbn_valid"] = bool(normalize_isbn(rec["isbn_raw"]))
            print(json.dumps(rec, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"   หน้ารายการ: ยาว {len(html)} ตัวอักษร")
    if crawl:
        rows = crawl_source(key, max_products=crawl, max_fetches=crawl * 4)
        print(f"\ncrawl ได้ {len(rows)} รายการ")
        for r in rows[:crawl]:
            print(" ", r["isbn_raw"], r["price"], r["list_price"], (r["title"] or "")[:50])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="robots | " + " | ".join(config.SOURCES))
    ap.add_argument("--crawl", type=int, default=0)
    a = ap.parse_args()
    check_robots() if a.target == "robots" else probe(a.target, a.crawl)
