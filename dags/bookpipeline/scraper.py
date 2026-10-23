"""ตัวดึงข้อมูลแบบสุภาพ: เช็ก robots.txt ทุก URL, หน่วงเวลา, ระบุตัวตนใน User-Agent, ไม่ใช้ Selenium"""
from __future__ import annotations

from pathlib import Path
import logging
import re
import time
from collections import deque
from urllib.parse import quote_plus, urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from . import config
from .parsers import in_scope, parse_product

log = logging.getLogger(__name__)


class BlockedError(RuntimeError):
    """เว็บปลายทางปฏิเสธการเข้าถึง (401/403) – ไม่พยายามเลี่ยง ให้ task ล้มเพื่อให้แหล่งอื่นทำงานต่อ"""


class PoliteFetcher:
    def __init__(self, user_agent=None, delay=None, timeout=None, session=None):
        self.ua = user_agent or config.USER_AGENT
        self.delay = config.REQUEST_DELAY if delay is None else delay
        self.timeout = timeout or config.REQUEST_TIMEOUT
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": self.ua, "Accept-Language": "th,en;q=0.8"})
        self._robots: dict[str, RobotFileParser] = {}
        self._last: dict[str, float] = {}
        self.skipped_by_robots = 0

    def _robots_for(self, url: str) -> RobotFileParser:
        p = urlparse(url)
        host = f"{p.scheme}://{p.netloc}"
        if host in self._robots:
            return self._robots[host]
        rp = RobotFileParser()
        try:
            r = self.session.get(host + "/robots.txt", timeout=self.timeout)
        except requests.RequestException as e:
            raise RuntimeError(f"อ่าน robots.txt ของ {host} ไม่ได้: {e}") from e
        if r.status_code == 200:
            rp.parse(r.text.splitlines())
        elif r.status_code in (404, 410):
            rp.parse([])  # ไม่มี robots.txt = ไม่มีข้อจำกัด
        else:  # 401/403/5xx: ถือว่าห้ามไว้ก่อน
            log.warning("robots.txt %s ตอบ %s -> ถือว่าห้ามเก็บ", host, r.status_code)
            rp.parse(["User-agent: *", "Disallow: /"])
        self._robots[host] = rp
        return rp

    def allowed(self, url: str) -> bool:
        return self._robots_for(url).can_fetch(self.ua, url)

    def get(self, url: str) -> str | None:
        if not self.allowed(url):
            self.skipped_by_robots += 1
            log.info("ข้าม (robots.txt ไม่อนุญาต): %s", url)
            return None
        host = urlparse(url).netloc
        for attempt in range(3):
            wait = self.delay - (time.monotonic() - self._last.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            try:
                r = self.session.get(url, timeout=self.timeout)
            except requests.RequestException as e:
                log.warning("request ล้มเหลว (%s) ครั้งที่ %d: %s", e, attempt + 1, url)
                self._last[host] = time.monotonic()
                time.sleep(2 ** attempt)
                continue
            self._last[host] = time.monotonic()
            if r.status_code in (401, 403):
                raise BlockedError(f"{url} ตอบ {r.status_code}")
            if r.status_code in (404, 410):
                return None
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(5 * (attempt + 1))
                continue
            r.encoding = "utf-8"
            return r.text
        return None


def _strip_query(u: str) -> str:
    return u.split("?")[0]


def extract_product_links(soup: BeautifulSoup, base_url: str, pattern: re.Pattern) -> list[str]:
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        u = _strip_query(urldefrag(urljoin(base_url, a["href"]))[0])
        if pattern.match(u) and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def crawl_source(key: str, cfg: dict | None = None, fetcher: PoliteFetcher | None = None,
                 max_products: int | None = None, max_fetches: int | None = None) -> list[dict]:
    """เริ่มจาก seed (+หน้า search ถ้ามี) แล้วไล่ตามลิงก์สินค้าที่เกี่ยวข้องแบบ BFS"""
    cfg = cfg or config.SOURCES[key]
    fetcher = fetcher or PoliteFetcher()
    max_products = max_products or config.MAX_PRODUCTS_PER_SOURCE
    max_fetches = max_fetches or config.MAX_FETCHES_PER_SOURCE
    pattern = re.compile(cfg["product_url_regex"])

    queue: deque[str] = deque(cfg["seeds"])
    for tpl in cfg.get("search_urls", []):
         for kw in config.SEARCH_KEYWORDS:
            queue.append(tpl.format(kw=quote_plus(kw)))

    seeds_file = cfg.get("seeds_file")
    if seeds_file:
        p = Path(__file__).with_name("seeds") / seeds_file
        if p.exists():
            queue.extend(l.strip() for l in p.read_text(encoding="utf-8").splitlines()
                         if l.strip() and not l.startswith("#"))
        else:
            log.warning("ไม่พบไฟล์ seed: %s", p)

    seen: set[str] = set()
    records: dict[str, dict] = {}
    fetches = 0

    while queue and fetches < max_fetches and len(records) < max_products:
        url = queue.popleft()
        norm = _strip_query(url) if pattern.match(_strip_query(url)) else url
        if norm in seen:
            continue
        seen.add(norm)

        try:
            html = fetcher.get(norm)
        except BlockedError:
            if not records:
                raise
            log.warning("%s: ถูกปฏิเสธระหว่างทาง หยุดไล่ต่อและใช้ข้อมูลที่ได้แล้ว", key)
            break
        fetches += 1
        if html is None:
            continue

        soup = BeautifulSoup(html, "lxml")
        links = extract_product_links(soup, norm, pattern)

        if pattern.match(norm):
            rec = parse_product(html, norm, key)
            if not rec or not rec.pop("_is_physical", True):
                continue
            if not in_scope(rec.get("title") or "", config.SCOPE_KEYWORDS):
                continue
            records[norm] = rec
            queue.extend(l for l in links if l not in seen)
        else:  # หน้ารายการ/ค้นหา: เก็บลิงก์สินค้าทั้งหมด
            queue.extend(l for l in links if l not in seen)

    log.info("%s: fetch %d หน้า, ได้สินค้า %d รายการ, ข้ามเพราะ robots %d", key, fetches, len(records), fetcher.skipped_by_robots)
    if not records:
        raise RuntimeError(f"{key}: ไม่ได้ข้อมูลสินค้าเลย (fetch {fetches} หน้า) – ตรวจ robots.txt/โครงสร้างหน้าเว็บด้วย scripts/probe.py")
    return list(records.values())
