import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dags"))
from bs4 import BeautifulSoup
from bookpipeline.scraper import PoliteFetcher

f = PoliteFetcher()
html = f.get(sys.argv[1])
if html is None:
    sys.exit("robots ไม่อนุญาต หรือ 404")
soup = BeautifulSoup(html, "lxml")

print("--- JSON-LD ---")
for s in soup.find_all("script", type="application/ld+json"):
    try:
        d = json.loads(s.string or "")
        print(json.dumps(d, ensure_ascii=False)[:700])
    except ValueError:
        print("(อ่านไม่ได้)")

text = soup.get_text("\n", strip=True)
print("\n--- ข้อความรอบ 'ข้อมูลสินค้า / สำนักพิมพ์ / ผู้แต่ง' ---")
for m in re.finditer(r"ข้อมูลสินค้า|สำนักพิมพ์|ผู้แต่ง", text):
    print(repr(text[max(0, m.start() - 10):m.end() + 120]))
    break
print("\n--- เลข 10-13 หลักในข้อความ ---")
print(re.findall(r"(?<!\d)\d{10,13}(?!\d)", text)[:10])