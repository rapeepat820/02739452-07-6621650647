"""ค่าตั้งต้นของ pipeline: แหล่งข้อมูล, ความสุภาพในการดึงข้อมูล, เกณฑ์คุณภาพ

แก้ค่าผ่านไฟล์ .env ได้ หรือ override แหล่งข้อมูลทั้งก้อนด้วย JSON ที่ชี้โดย
ตัวแปรสภาพแวดล้อม SOURCES_OVERRIDE_FILE (สะดวกเวลาปรับ regex/seed โดยไม่ต้อง build ใหม่)
"""
import json
import os

USER_AGENT = os.environ.get(
    "SCRAPER_USER_AGENT",
    "KU-KPS-02739452-StudentBot/1.0 (course project; contact: set SCRAPER_USER_AGENT in .env)",
)
REQUEST_DELAY = float(os.environ.get("REQUEST_DELAY_SECONDS", "1.5"))
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "20"))
MAX_PRODUCTS_PER_SOURCE = int(os.environ.get("MAX_PRODUCTS_PER_SOURCE", "100"))
MAX_FETCHES_PER_SOURCE = int(os.environ.get("MAX_FETCHES_PER_SOURCE", "300"))

EXTRACT_RETRIES = int(os.environ.get("EXTRACT_RETRIES", "2"))
EXTRACT_RETRY_DELAY_SECONDS = int(os.environ.get("EXTRACT_RETRY_DELAY_SECONDS", "30"))

QUALITY_MAX_INVALID_RATIO = float(os.environ.get("QUALITY_MAX_INVALID_RATIO", "0.25"))
QUALITY_MIN_ROWS = int(os.environ.get("QUALITY_MIN_ROWS", "20"))

# ขอบเขตหัวข้อ: เก็บเฉพาะหนังสือที่ชื่อมีคำเหล่านี้ (ไม่สนตัวพิมพ์เล็ก/ใหญ่)
# ปรับให้ตรงกับขอบเขตที่คุณจองไว้ในกลุ่มไลน์
SCOPE_KEYWORDS = [
    k.strip().lower()
    for k in os.environ.get(
        "SCOPE_KEYWORDS",
        "python,ไพธอน,java,sql,data,ข้อมูล,machine learning,deep learning,ai,"
        "โปรแกรม,programming,coding,docker,linux,cloud,web,developer",
    ).split(",")
    if k.strip()
]

# คำค้นสำหรับหน้า search (ถ้าร้านนั้นมี search_urls)
SEARCH_KEYWORDS = [
    k.strip() for k in os.environ.get("SEARCH_KEYWORDS", "python,data science,machine learning,sql").split(",") if k.strip()
]

# หมายเหตุ: โครงสร้างหน้าเว็บของแต่ละร้านตรวจจากหน้าสินค้าตัวอย่างเท่านั้น
# ถ้า scraper ได้ข้อมูลน้อย ให้รัน  python scripts/probe.py <source>  เพื่อดูว่า parse อะไรได้บ้าง
SOURCES = {
     "b2s": {
        "label": "B2S",
        "seeds": ["https://www.b2s.co.th/book/wisdom/computer.html"],
        "seeds_file": "b2s.txt",
        "search_urls": [],
        "product_url_regex": r"^https://www\.b2s\.co\.th/(?:\d{6,13}\.html|product/[^?#\s]+-p\.[A-Za-z0-9]+)$",

    },
    "seed": {
        "label": "Se-ed",
        "seeds_file": "seed.txt",
        "seeds": [
            "https://www.se-ed.com/physical/%E0%B8%84%E0%B8%B1%E0%B8%A1%E0%B8%A0%E0%B8%B5%E0%B8%A3%E0%B9%8C-Python-%E0%B8%89%E0%B8%9A%E0%B8%B1%E0%B8%9A%E0%B8%9B%E0%B8%A3%E0%B8%B1%E0%B8%9A%E0%B8%9B%E0%B8%A3%E0%B8%B8%E0%B8%87-z9qyk2qhht8v18o4bbdz",
            "https://www.se-ed.com/physical/%E0%B8%84%E0%B8%B9%E0%B9%88%E0%B8%A1%E0%B8%B7%E0%B8%AD%E0%B9%80%E0%B8%82%E0%B8%B5%E0%B8%A2%E0%B8%99%E0%B9%82%E0%B8%9B%E0%B8%A3%E0%B9%81%E0%B8%81%E0%B8%A3%E0%B8%A1%E0%B8%94%E0%B9%89%E0%B8%A7%E0%B8%A2-Python-f3isswy0imswg0c9w4nb",
            "https://www.se-ed.com/physical/%E0%B9%80%E0%B8%A3%E0%B8%B5%E0%B8%A2%E0%B8%99-Coding-%E0%B8%A3%E0%B8%B0%E0%B8%94%E0%B8%B1%E0%B8%9A%E0%B9%80%E0%B8%A3%E0%B8%B4%E0%B9%88%E0%B8%A1%E0%B8%95%E0%B9%89%E0%B8%99%E0%B8%94%E0%B9%89%E0%B8%A7%E0%B8%A2-Python-pf12gidugmquqg3t5rld",
            "https://www.se-ed.com/physical/%E0%B9%80%E0%B8%A3%E0%B8%B5%E0%B8%A2%E0%B8%99%E0%B8%A3%E0%B8%B9%E0%B9%89-Data-Science-%E0%B9%81%E0%B8%A5%E0%B8%B0-AI-:-Machine-Learning-%E0%B8%94%E0%B9%89%E0%B8%A7%E0%B8%A2-Python-xk8pqdi7nbzdto026imq",
        ],
        # หน้า search ของ Se-ed วาดด้วย JavaScript จึงไม่ใช้ ให้ไล่ตามลิงก์ "สินค้าแนะนำ" ในหน้าสินค้าแทน
        "search_urls": [],
        "product_url_regex": r"^https://www\.se-ed\.com/physical/[^?#\s]+$",
    },
    "naiin": {
        "label": "Naiin",
        "seeds": [
            "https://www.naiin.com/product/detail/665396",
            "https://www.naiin.com/product/detail/614175",
        ],
        "search_urls": ["https://www.naiin.com/search-result?title={kw}"],
        "product_url_regex": r"^https://www\.naiin\.com/product/detail/\d+$",
    },
}

SOURCES.pop("b2s", None)  # B2S ไม่แสดง ISBN ในหน้าสินค้า จับคู่ข้ามร้านไม่ได้

_override = os.environ.get("SOURCES_OVERRIDE_FILE")
if _override and os.path.exists(_override):
    with open(_override, encoding="utf-8") as f:
        SOURCES = json.load(f)
