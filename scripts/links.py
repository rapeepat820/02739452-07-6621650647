import re, sys
import requests
from bs4 import BeautifulSoup

UA = "KU-KPS-02739452-StudentBot/1.0 (course project)"
for url in sys.argv[1:]:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    r.encoding = "utf-8"
    soup = BeautifulSoup(r.text, "lxml")
    hrefs = [a["href"] for a in soup.find_all("a", href=True)]
    prod = [h for h in hrefs if "/product/detail/" in h]
    print(f"\n{url}\n  HTTP {r.status_code}, ยาว {len(r.text)}, ลิงก์ทั้งหมด {len(hrefs)}, ลิงก์สินค้า {len(prod)}")
    for h in prod[:8]:
        print("   ", h)
    print("   ตัวอย่างลิงก์อื่น:", [h for h in hrefs if "/product/detail/" not in h][:6])