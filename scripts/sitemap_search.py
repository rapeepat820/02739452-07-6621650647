import gzip, re, sys
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dags"))
from bookpipeline.scraper import PoliteFetcher

# ใช้:  python scripts/sitemap_search.py "<คำค้น,คั่นด้วยจุลภาค>" <sitemap url> [<sitemap url> ...]
keywords = [k.strip().lower() for k in sys.argv[1].split(",") if k.strip()]
f = PoliteFetcher()
hits, total = [], 0
for sm in sys.argv[2:]:
    if not f.allowed(sm):
        print("robots ไม่อนุญาต:", sm)
        continue
    r = f.session.get(sm, timeout=60)
    data = gzip.decompress(r.content) if r.content[:2] == b"\x1f\x8b" else r.content
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", data.decode("utf-8", "replace"))
    total += len(locs)
    print(f"{sm} -> HTTP {r.status_code}, {len(locs)} URL")
    hits += [u for u in locs if any(k in unquote(u).lower() for k in keywords)]

print(f"\nรวม {total} URL, ตรงคำค้น {len(hits)}")
for u in hits[:15]:
    print("  ", unquote(u))
Path("sitemap_hits.txt").write_text("\n".join(hits), encoding="utf-8")
print("บันทึกทั้งหมดไว้ที่ sitemap_hits.txt")