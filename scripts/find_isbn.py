import re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dags"))
from bs4 import BeautifulSoup
from bookpipeline.scraper import PoliteFetcher

f = PoliteFetcher()
html = f.get(sys.argv[1])
if html is None:
    sys.exit("robots ไม่อนุญาต หรือ 404")

print("--- เลข 978/979 ในโค้ดดิบ ---")
for m in re.finditer(r"97[89][\d-]{10,14}", html):
    s = max(0, m.start() - 70)
    print(repr(html[s:m.end() + 30]))

text = BeautifulSoup(html, "lxml").get_text("\n", strip=True)
print("\n--- ข้อความรอบคำว่า ISBN / บาร์โค้ด / รหัสสินค้า ---")
for m in re.finditer(r"ISBN|บาร์โค้ด|Barcode|รหัสสินค้า", text, re.I):
    print(repr(text[max(0, m.start() - 20):m.end() + 60]))