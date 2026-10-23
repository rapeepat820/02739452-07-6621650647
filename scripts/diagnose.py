import re, sys
from pathlib import Path
from urllib.parse import urljoin, urldefrag, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dags"))
from bs4 import BeautifulSoup
from bookpipeline.scraper import PoliteFetcher

f = PoliteFetcher()
host = "{0.scheme}://{0.netloc}".format(urlparse(sys.argv[1]))

r = f.session.get(host + "/robots.txt", timeout=20)
print(f"robots.txt -> HTTP {r.status_code}")
for line in r.text.splitlines():
    if re.match(r"(?i)\s*(user-agent|disallow|allow|crawl-delay|sitemap)", line):
        print("   ", line)

for url in sys.argv[1:]:
    ok = f.allowed(url)
    print(f"\n{'อนุญาต' if ok else 'ห้าม   '} {url}")
    if not ok:
        continue
    resp = f.session.get(url, timeout=20)
    resp.encoding = "utf-8"
    print("   HTTP", resp.status_code, "ยาว", len(resp.text))
    soup = BeautifulSoup(resp.text, "lxml")
    hrefs = {urldefrag(urljoin(url, a["href"]))[0] for a in soup.find_all("a", href=True)}
    same = sorted(h for h in hrefs if urlparse(h).netloc == urlparse(url).netloc)
    print("   ลิงก์ในเว็บเดียวกัน:", len(same))
    for h in [h for h in same if re.search(r"/\d{6,13}\.html|/product/", h)][:12]:
        print("      ", h)