import html
import sys
from pathlib import Path
from urllib.parse import unquote

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "dags"))
from bookpipeline.parsers import in_scope  # noqa: E402  (คำอังกฤษต้องตรงทั้งคำ)

PREFIX = "https://www.se-ed.com/physical/"
OUT_NAME = "seed.txt"
LIMIT = 400

KEYWORDS = [
    "python", "ไพธอน", "java", "javascript", "typescript", "sql", "mysql", "postgresql", "mongodb",
    "docker", "kubernetes", "linux", "react", "django", "flask", "html", "css", "php", "git",
    "programming", "coding", "machine learning", "deep learning", "data science", "data analytics",
    "data engineering", "power bi", "tableau", "excel", "arduino", "raspberry",
    "เขียนโปรแกรม", "เขียนโค้ด", "ฐานข้อมูล", "คอมพิวเตอร์",
]
EXCLUDE = ["bag", "purse", "tote", "artist", "tiktok", "stock", "trading", "เงินล้าน", "หุ้น",
           "ขายของ", "การ์ตูน", "นิทาน", "ระบายสี"]

hits = (root / "sitemap_hits.txt").read_text(encoding="utf-8").split()
seen, out = set(), []
for u in hits:
    d = html.unescape(unquote(u))
    if not d.startswith(PREFIX) or "&" in d or "#" in d or "?" in d:
        continue  # เฉพาะหนังสือเล่ม และตัด URL ที่มีอักขระพิเศษ
    slug = d[len(PREFIX):].rsplit("-", 1)[0].replace("-", " ")  # ตัดรหัสสุ่มท้าย URL
    low = slug.lower()
    if any(x in low for x in EXCLUDE) or not in_scope(slug, KEYWORDS):
        continue
    if u in seen:
        continue
    seen.add(u)
    out.append(u)

print(f"ผ่านตัวกรอง {len(out)} URL (จะใช้ {min(len(out), LIMIT)})")
out = out[:LIMIT]
dest = root / "dags" / "bookpipeline" / "seeds"
dest.mkdir(parents=True, exist_ok=True)
(dest / OUT_NAME).write_text("\n".join(out) + "\n", encoding="utf-8")
print("->", dest / OUT_NAME)
for u in out[:20]:
    print("  ", html.unescape(unquote(u))[len(PREFIX):])