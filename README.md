# 02739452 – ระบบรวบรวมราคาหนังสือคอมพิวเตอร์/โปรแกรมมิ่งจากหลายร้าน

> วิชา แพลตฟอร์มข้อมูลขนาดใหญ่และการวิเคราะห์ (02739452) – ข้อสอบปลายภาค ภาคต้น 2569
> ผู้จัดทำ: รพีภัทร หงษ์วิชุลดา 6621650647 ลำดับนิสิต 07 820

## หัวข้อ
| รายการ | รายละเอียด |
|---|---|
| หมวด | ราคาหนังสือ |
| ขอบเขต | หนังสือ**ฉบับเล่ม (ปกอ่อน)** หมวดคอมพิวเตอร์/โปรแกรมมิ่ง (Python, Data, AI, SQL ฯลฯ) ← ปรับให้ตรงกับที่จองในไลน์ |
| คีย์กลาง | **ISBN-13** (ตรวจ check digit, รองรับ ISBN-10 โดยแปลงเป็น 13) |

## แหล่งข้อมูลที่ใช้งานจริง
| แหล่ง | รหัสใน DAG | วิธีได้ URL หน้าสินค้า | ข้อมูลที่ได้ |
|---|---|---|---|
| **Se-ed** (https://www.se-ed.com) | `seed` | ดึงรายชื่อ URL จาก sitemap ของร้านเอง แล้วกรองเฉพาะหนังสือเล่มหมวดคอมพิวเตอร์ (`scripts/build_seeds.py` → `dags/bookpipeline/seeds/seed.txt`) | ISBN (จาก JSON-LD `sku`), ชื่อ, ราคา, สถานะสต็อก |
| **Naiin** (https://www.naiin.com) | `naiin` | รายการ URL หน้าสินค้าที่รวบรวมไว้ใน `dags/bookpipeline/seeds/naiin.txt` | ISBN (จากช่อง "บาร์โค้ด"), ชื่อ, ราคา, ราคาปก, สำนักพิมพ์ |

การดึงข้อมูล: `requests` + `BeautifulSoup` (**ไม่ใช้ Selenium**) อ่าน JSON-LD (`offers.price`, `sku`) และข้อความในหน้าสินค้า

### แหล่งที่ลองแล้วแต่ไม่ได้ใช้
- **B2S** – robots.txt อนุญาต และมี sitemap แต่ **หน้าสินค้าไม่แสดง ISBN** (มีแต่รหัสภายในเช่น `D092151`) จึงจับคู่ข้ามร้านและตัดซ้ำด้วย ISBN ไม่ได้ ตั้งค่าไว้ใน `config.py` แต่ปิดไว้ด้วย `SOURCES.pop("b2s", None)`
- **sitemap ของ Naiin** – ไฟล์อยู่ที่ `storage.naiin.com` ซึ่ง robots.txt ตอบ 403 โค้ดจึงถือว่าห้ามเก็บและไม่ใช้ (ใช้เฉพาะหน้าสินค้าบน `www.naiin.com` ที่ robots.txt อนุญาต)
- หน้าค้นหาของ Naiin และ Se-ed วาดด้วย JavaScript จึงไม่ใช้เป็นตัวหา URL

### การปฏิบัติตาม robots.txt และ PDPA
- โค้ดเช็ก `robots.txt` **ทุก URL** ก่อนดึง (`PoliteFetcher.allowed`) URL ที่ไม่อนุญาตจะถูกข้าม และถ้า robots.txt ตอบ 401/403/5xx จะถือว่าห้ามเก็บ
- หน่วงเวลา 1.5 วินาทีต่อคำขอ ระบุตัวตนใน User-Agent ถ้าโดน 401/403 จะหยุดทันที ไม่พยายามเลี่ยง
- เก็บเฉพาะข้อมูลสินค้า (ชื่อ, ISBN, สำนักพิมพ์, ราคา, สต็อก, URL) **ไม่เก็บข้อมูลส่วนบุคคล** เช่น รีวิวหรือชื่อผู้ใช้
- เก็บเฉพาะฉบับเล่ม เพราะ e-book มี ISBN คนละเลขกับฉบับพิมพ์ ทำให้จับคู่ข้ามร้านไม่ได้

## สถาปัตยกรรม
```
 Se-ed ─┐
        ├─► [extract → transform] ต่อแหล่ง (TaskGroup รันขนาน)
 Naiin ─┘            │
                     ▼
              stage_data  (trigger_rule = all_done: แหล่งไหนล่ม ข้ามแล้วไปต่อ)
                     ▼
              quality_check  (Branch)
                ├─ ผ่าน ──► promote_valid ─────┐   UPSERT (isbn, source) แถวเสีย → rejected_rows
                └─ ไม่ผ่าน ► quarantine_batch ──┤   ไม่แตะตารางหลัก ส่งทั้งชุดไป rejected_rows
                                               ▼
                                          finalize  → books_unique (ตัดซ้ำข้ามแหล่งด้วย ISBN) + pipeline_runs

   PostgreSQL: book_prices · staging_prices · rejected_rows · books_unique · pipeline_runs
                                      │
                      Streamlit dashboard (อ่านจาก PostgreSQL โดยตรง)
```

| ระดับ | สิ่งที่ทำ | อยู่ที่ไหน |
|---|---|---|
| 1 | extract → transform → load → PostgreSQL → เว็บแสดงตารางและกราฟ | `dags/book_price_pipeline.py`, `web/app.py` |
| 2 | 2 แหล่งรันขนานด้วย TaskGroup, schema เดียวกัน, UPSERT `(isbn, source)`, KPI + ตัวกรอง | TaskGroup `scrape`, `storage.upsert_prices`, แท็บ "ภาพรวม" |
| 3 (บางส่วน) | แหล่งล่มแล้วไปต่อ, ตัดซ้ำข้ามแหล่งด้วย ISBN, ตรวจคุณภาพแล้วแตกเส้นทาง | `stage_data`, `books_unique`, `quality_check` → `promote_valid` / `quarantine_batch` |
| โบนัส | หน้าสถานะ pipeline บนเว็บ | แท็บ "สถานะ pipeline" (ตาราง `pipeline_runs`) |

**หมายเหตุระดับ 3:** โจทย์ต้องการ 3 แหล่ง รอบนี้ใช้งานจริง **2 แหล่ง** (แหล่งที่สามตัดออกเพราะเวลาจำกัด) กลไกทั้งหมดข้างต้นทำงานกับ 2 แหล่ง และ DAG สร้าง TaskGroup จากรายการใน `config.SOURCES` จึงเพิ่มแหล่งที่สามได้โดยเพิ่มส่วนตั้งค่าใน `dags/bookpipeline/config.py` โดยไม่ต้องแก้ DAG

### เกณฑ์ตรวจคุณภาพ (ตั้งค่าใน `.env`)
แถวเสียคือ ISBN ไม่ถูกต้อง / ราคาว่างหรือ ≤ 0 / ไม่มีชื่อ
- แถวเสีย ≤ 25% และแถวรวม ≥ 20 → **promote_valid**: UPSERT แถวดีเข้า `book_prices` แถวเสียไป `rejected_rows`
- นอกเกณฑ์ → **quarantine_batch**: ไม่แตะตารางหลัก ส่งทั้งชุดไป `rejected_rows` พร้อมเหตุผล

## วิธีรัน
ต้องมี Docker + Docker Compose

```bash
git clone <repo-url> && cd <repo>
cp .env.example .env          # แก้รหัสผ่าน และ SCRAPER_USER_AGENT ใส่อีเมลติดต่อจริง
docker compose up -d --build
```
| บริการ | URL | หมายเหตุ |
|---|---|---|
| Airflow | http://localhost:8080 | ผู้ใช้/รหัสผ่านตาม `.env` (`AIRFLOW_ADMIN_*`) |
| Dashboard | http://localhost:8501 | อ่านจาก PostgreSQL โดยตรง |
| PostgreSQL | localhost:5433 | DB `books` |

1. รอให้ Airflow พร้อม (`docker compose ps` ขึ้น healthy ราว 1–2 นาที)
2. เปิด DAG `book_price_pipeline` (เปิดใช้งานไว้ให้แล้ว) กด **Trigger** (หรือรอ schedule 06:00)
3. ดู Graph view / Grid view ที่หน้า DAG รอบแรกใช้เวลาประมาณ 5–10 นาที (หน่วงเวลาสุภาพ)
4. เปิด Dashboard เพื่อดูผล

จำนวนข้อมูลต่อแหล่งกำหนดด้วย `MAX_PRODUCTS_PER_SOURCE` และ `MAX_FETCHES_PER_SOURCE` ใน `.env`

### ทดสอบกรณีแหล่งล่ม
Trigger DAG แบบมี config: `{"fail_sources": ["naiin"]}` → task `scrape.naiin.extract` ล้ม แต่ DAG ยังรวมข้อมูลจาก Se-ed ต่อ สถานะรอบนั้นเป็น `partial_success` ในหน้าสถานะ pipeline

### ทดสอบว่ารันซ้ำแล้วแถวไม่เพิ่ม (UPSERT)
```bash
docker compose exec postgres psql -U <POSTGRES_USER> -d books -c "select source, count(*) from book_prices group by 1"
# Trigger DAG อีกรอบ แล้วรันคำสั่งเดิม จำนวนแถวต้องไม่เพิ่ม (ยกเว้นพบหนังสือเล่มใหม่)
```

## เครื่องมือช่วยตรวจแหล่งข้อมูล (`scripts/`)
```bash
pip install -r requirements-airflow.txt
python scripts/probe.py robots              # ดู robots.txt ของทุกร้าน
python scripts/probe.py seed --crawl 10     # ลอง fetch + parse จริง (ใช้ได้กับ naiin)
python scripts/diagnose.py <url>            # ดู robots.txt + ลิงก์ในหน้า
python scripts/sitemap.py <sitemap-url>     # ดูโครงสร้าง sitemap
python scripts/sitemap_search.py "<คำค้น>" <sitemap-url> ...   # ค้นชื่อหนังสือใน sitemap
python scripts/build_seeds.py               # กรอง URL เป็นไฟล์ seed ของ Se-ed
python scripts/add_naiin_seeds.py           # แปลง naiin_urls.txt เป็นไฟล์ seed ของ Naiin
```
ถ้าร้านใดตอบ 403 หรือ robots.txt ห้ามเก็บ ให้เปลี่ยนแหล่ง อย่าพยายามเลี่ยง

### เทสต์
```bash
pip install -r requirements.txt && python -m pytest -q tests
```

## โครงสร้างโฟลเดอร์
```
dags/
  book_price_pipeline.py      # DAG
  bookpipeline/               # config, scraper, parsers, transform, quality, storage, schema.sql
  bookpipeline/seeds/         # seed.txt (Se-ed), naiin.txt (Naiin)
web/app.py                    # Streamlit dashboard
docker-compose.yml  Dockerfile.airflow  web/Dockerfile
requirements.txt  .env.example
scripts/  tests/  docs/
```

## ข้อจำกัดที่ทราบ
- ราคาในแต่ละร้านเป็นราคา ณ เวลาที่ดึง (`scraped_at`) อาจเป็นราคาลดไม่ใช่ราคาปก
- หน้าสินค้า Se-ed ไม่มีราคาปกและสำนักพิมพ์ใน HTML (คอลัมน์ `list_price` และ `publisher` จึงว่างสำหรับ Se-ed) ส่วนตัวกรองสำนักพิมพ์และ KPI ส่วนลดจึงอาศัยข้อมูลจาก Naiin
- โครงสร้างหน้าเว็บร้านค้าเปลี่ยนได้ ถ้า parser ได้ข้อมูลน้อยลง ระบบจะเข้าเส้นทาง quarantine แทนที่จะเขียนข้อมูลเสียลงตารางหลัก
- รายการ URL ใน `seeds/` เป็นภาพตัดขวาง ณ เวลาที่รวบรวม หากร้านถอดสินค้า หน้านั้นจะตอบ 404 และถูกข้ามอัตโนมัติ
