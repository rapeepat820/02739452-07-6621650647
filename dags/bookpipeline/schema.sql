-- ตารางหลัก: 1 แถว = 1 เล่ม ต่อ 1 ร้าน  (UPSERT ด้วย isbn+source ทำให้รันซ้ำแล้วจำนวนแถวไม่เพิ่ม)
CREATE TABLE IF NOT EXISTS book_prices (
    isbn        TEXT        NOT NULL CHECK (isbn ~ '^97[89][0-9]{10}$'),
    source      TEXT        NOT NULL,
    title       TEXT        NOT NULL,
    publisher   TEXT,
    price       NUMERIC(10,2) NOT NULL CHECK (price > 0),
    list_price  NUMERIC(10,2),
    in_stock    BOOLEAN,
    url         TEXT        NOT NULL,
    scraped_at  TIMESTAMPTZ NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (isbn, source)
);

-- ตารางพักข้อมูลของแต่ละ run (ใช้ตรวจคุณภาพก่อนเข้าตารางหลัก)
CREATE TABLE IF NOT EXISTS staging_prices (
    run_id      TEXT NOT NULL,
    source      TEXT NOT NULL,
    isbn_raw    TEXT,
    isbn        TEXT,
    title       TEXT,
    publisher   TEXT,
    price       NUMERIC(10,2),
    list_price  NUMERIC(10,2),
    in_stock    BOOLEAN,
    url         TEXT,
    scraped_at  TIMESTAMPTZ,
    issues      TEXT
);
CREATE INDEX IF NOT EXISTS idx_staging_run ON staging_prices(run_id);

-- แถวที่ไม่ผ่านการตรวจคุณภาพ
CREATE TABLE IF NOT EXISTS rejected_rows (
    id          BIGSERIAL PRIMARY KEY,
    run_id      TEXT NOT NULL,
    source      TEXT,
    isbn_raw    TEXT,
    title       TEXT,
    price       NUMERIC(10,2),
    url         TEXT,
    reason      TEXT,
    rejected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ตัดรายการซ้ำข้ามแหล่ง: 1 แถว = 1 ISBN
CREATE TABLE IF NOT EXISTS books_unique (
    isbn            TEXT PRIMARY KEY,
    title           TEXT,
    publisher       TEXT,
    n_sources       INT NOT NULL,
    min_price       NUMERIC(10,2),
    max_price       NUMERIC(10,2),
    price_spread    NUMERIC(10,2),
    cheapest_source TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- สถานะ pipeline แต่ละรอบ (โบนัส: หน้าสถานะ pipeline บนเว็บ)
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id          TEXT PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'running',
    sources_ok      TEXT[],
    sources_failed  TEXT[],
    rows_staged     INT,
    rows_loaded     INT,
    rows_rejected   INT,
    quality_passed  BOOLEAN,
    note            TEXT
);
