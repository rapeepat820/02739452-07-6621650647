import re, sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dags"))
from bs4 import BeautifulSoup
from bookpipeline.scraper import PoliteFetcher

f = PoliteFetcher()
url = sys.argv[1]
host = "{0.scheme}://{0.netloc}".format(urlparse(url))

robots = f.session.get(host + "/robots.txt", timeout=20).text
print("Sitemap ใน robots.txt:", [l for l in robots.splitlines() if l.lower().startswith("sitemap")])

html = f.get(url)
if html is None:
    sys.exit("robots.txt ไม่อนุญาต หรือ 404")
print("ความยาว:", len(html))
ids = sorted(set(re.findall(r"/product/detail/(\d+)", html)))
print("เลขสินค้าที่พบในข้อความดิบ:", len(ids), ids[:10])
for kw in ("__NEXT_DATA__", "productCode", "barcode", "isbn"):
    print(f"มีคำว่า {kw}:", kw in html)
for s in BeautifulSoup(html, "lxml").find_all("script"):
    t = s.string or ""
    if len(t) > 5000:
        print("script ใหญ่:", s.get("id"), s.get("type"), len(t), "|", t[:120].replace("\n", " "))