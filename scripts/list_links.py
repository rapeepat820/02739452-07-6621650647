import sys
from pathlib import Path
from urllib.parse import urljoin, urldefrag

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dags"))
from bs4 import BeautifulSoup
from bookpipeline.scraper import PoliteFetcher

f = PoliteFetcher()
url = sys.argv[1]
html = f.get(url)
if html is None:
    sys.exit("robots ไม่อนุญาต หรือ 404")
soup = BeautifulSoup(html, "lxml")
links = sorted({urldefrag(urljoin(url, a["href"]))[0] for a in soup.find_all("a", href=True)})
print(len(links), "ลิงก์")
for l in links:
    print(l)