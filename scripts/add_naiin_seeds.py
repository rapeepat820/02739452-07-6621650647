import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
pat = re.compile(r"^https://www\.naiin\.com/product/detail/\d+$")
seen, ok, bad = set(), [], []
for line in (root / "naiin_urls.txt").read_text(encoding="utf-8").splitlines():
    u = line.strip().split("?")[0].rstrip("/")
    if not u:
        continue
    if not pat.match(u):
        bad.append(u)
    elif u not in seen:
        seen.add(u)
        ok.append(u)

dest = root / "dags" / "bookpipeline" / "seeds"
dest.mkdir(parents=True, exist_ok=True)
(dest / "naiin.txt").write_text("\n".join(ok) + "\n", encoding="utf-8")
print(f"ใช้ได้ {len(ok)} URL -> {dest / 'naiin.txt'}")
for b in bad:
    print("รูปแบบไม่ถูกต้อง (ข้าม):", b)