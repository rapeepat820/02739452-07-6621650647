import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dags"))
from bookpipeline.scraper import crawl_source

rows = crawl_source("seed", max_products=40, max_fetches=60)
lines = [f"{r['isbn_raw']}\t{r['title']}" for r in rows if r.get("isbn_raw")]
Path("isbn_list.txt").write_text("\n".join(lines), encoding="utf-8")
print(len(lines), "เล่ม -> isbn_list.txt")
print("\n".join(lines))