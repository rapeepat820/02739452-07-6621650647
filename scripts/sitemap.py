import gzip, re, sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dags"))
from bookpipeline.scraper import PoliteFetcher

f = PoliteFetcher()
url = sys.argv[1]
if not f.allowed(url):
    sys.exit("robots.txt ไม่อนุญาตให้ดึง " + url)
r = f.session.get(url, timeout=30)
data = r.content
if data[:2] == b"\x1f\x8b":
    data = gzip.decompress(data)
xml = data.decode("utf-8", "replace")
locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
print("HTTP", r.status_code, "| sitemapindex:", "<sitemapindex" in xml, "| จำนวน <loc>:", len(locs))
for l in locs[:12]:
    print("  ", l)
paths = Counter("/".join(urlparse(l).path.split("/")[:3]) for l in locs)
print("รูปแบบ path:", paths.most_common(6))