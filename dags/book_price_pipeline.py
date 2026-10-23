"""
DAG: book_price_pipeline
รวบรวมราคาหนังสือคอมพิวเตอร์/โปรแกรมมิ่งจาก 3 ร้าน (B2S, Se-ed, Naiin) -> PostgreSQL

ระดับ 1  extract -> transform -> load -> PostgreSQL
ระดับ 2  TaskGroup ต่อแหล่ง รันขนานกัน, schema เดียวกัน, UPSERT (isbn, source)
ระดับ 3  แหล่งใดล่ม DAG รวมข้อมูลจากแหล่งที่เหลือต่อ (trigger_rule=all_done),
         ตัดซ้ำข้ามแหล่งด้วย ISBN (books_unique), ตรวจคุณภาพแล้วแตกเส้นทาง (BranchPythonOperator)
โบนัส   หน้าสถานะ pipeline บนเว็บ (ตาราง pipeline_runs)

ทดสอบกรณีแหล่งล่ม: Trigger DAG w/ config  {"fail_sources": ["naiin"]}
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import pendulum
from airflow import DAG
from airflow.decorators import task
from airflow.exceptions import AirflowFailException
from airflow.operators.python import get_current_context
from airflow.utils.task_group import TaskGroup
from airflow.utils.trigger_rule import TriggerRule

from bookpipeline import config, quality, storage
from bookpipeline.scraper import crawl_source
from bookpipeline.transform import transform_rows

DATA_DIR = Path(os.environ.get("PIPELINE_DATA_DIR", "/opt/airflow/data"))
SOURCES = list(config.SOURCES.keys())


def _work_path(run_id: str, source: str, stage: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", run_id)
    d = DATA_DIR / safe
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{stage}_{source}.json"


def _write_json(path: Path, rows: list[dict]) -> str:
    path.write_text(json.dumps(rows, ensure_ascii=False, default=str), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------- tasks
@task
def init_run() -> str:
    ctx = get_current_context()
    run_id = ctx["run_id"]
    storage.ensure_schema()
    storage.start_run(run_id)
    return run_id


@task(retries=config.EXTRACT_RETRIES, retry_delay=timedelta(seconds=config.EXTRACT_RETRY_DELAY_SECONDS),
      execution_timeout=timedelta(minutes=40))
def extract(source: str) -> str:
    ctx = get_current_context()
    conf = ctx["dag_run"].conf or {}
    if source in (conf.get("fail_sources") or []):
        raise RuntimeError(f"จำลองว่าแหล่ง {source} ล่ม (dag_run.conf.fail_sources)")
    rows = crawl_source(source)
    return _write_json(_work_path(ctx["run_id"], source, "raw"), rows)


@task
def transform(source: str, raw_path: str) -> str:
    ctx = get_current_context()
    rows = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    clean = transform_rows(rows)
    return _write_json(_work_path(ctx["run_id"], source, "clean"), clean)


@task(trigger_rule=TriggerRule.ALL_DONE)
def stage_data() -> dict:
    """รวมผลจากทุกแหล่งที่สำเร็จ (แหล่งที่ล่มถูกข้าม) แล้วพักไว้ใน staging_prices"""
    ctx = get_current_context()
    ti, run_id = ctx["ti"], ctx["run_id"]
    ok, failed, rows = [], [], []
    for src in SOURCES:
        path = ti.xcom_pull(task_ids=f"scrape.{src}.transform")
        if path and Path(path).exists():
            rows.extend(json.loads(Path(path).read_text(encoding="utf-8")))
            ok.append(src)
        else:
            failed.append(src)
    if not ok:
        storage.update_run(run_id, status="failed", sources_ok=[], sources_failed=failed,
                           finished_at=datetime.utcnow(), note="ทุกแหล่งล่ม")
        raise AirflowFailException("ทุกแหล่งข้อมูลล่ม ไม่มีข้อมูลให้รวม")
    storage.stage_rows(run_id, rows)
    storage.update_run(run_id, sources_ok=ok, sources_failed=failed, rows_staged=len(rows))
    return {"sources_ok": ok, "sources_failed": failed, "rows": len(rows)}


@task.branch
def quality_check() -> str:
    ctx = get_current_context()
    rows = storage.fetch_staging(ctx["run_id"])
    result = quality.evaluate(rows, config.QUALITY_MAX_INVALID_RATIO, config.QUALITY_MIN_ROWS)
    ctx["ti"].xcom_push(key="quality", value=result)
    return "promote_valid" if result["passed"] else "quarantine_batch"


@task
def promote_valid() -> dict:
    """ผ่านเกณฑ์: UPSERT แถวที่ถูกต้องเข้า book_prices, แถวเสียส่งไป rejected_rows"""
    run_id = get_current_context()["run_id"]
    rows = storage.fetch_staging(run_id)
    good = [r for r in rows if not r["issues"] and r["isbn"]]
    bad = [r for r in rows if r["issues"] or not r["isbn"]]
    loaded = storage.upsert_prices(good)
    rejected = storage.insert_rejected(run_id, bad)
    return {"loaded": loaded, "rejected": rejected}


@task
def quarantine_batch() -> dict:
    """ไม่ผ่านเกณฑ์: ไม่แตะตารางหลัก ส่งทั้งชุดไป rejected_rows เพื่อตรวจสอบ"""
    ctx = get_current_context()
    run_id = ctx["run_id"]
    q = ctx["ti"].xcom_pull(task_ids="quality_check", key="quality") or {}
    rows = storage.fetch_staging(run_id)
    rejected = storage.insert_rejected(run_id, rows, reason="batch_failed_quality: " + "; ".join(q.get("reasons", [])))
    return {"loaded": 0, "rejected": rejected}


@task(trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS)
def finalize() -> None:
    ctx = get_current_context()
    ti, run_id = ctx["ti"], ctx["run_id"]
    q = ti.xcom_pull(task_ids="quality_check", key="quality") or {}
    staged = ti.xcom_pull(task_ids="stage_data") or {}
    outcome = ti.xcom_pull(task_ids="promote_valid") or ti.xcom_pull(task_ids="quarantine_batch") or {}

    unique_isbns = storage.rebuild_books_unique()
    storage.drop_staging(run_id)

    if not q.get("passed", False):
        status = "quarantined"
    elif staged.get("sources_failed"):
        status = "partial_success"
    else:
        status = "success"
    note = f"ISBN ไม่ซ้ำ {unique_isbns}; " + ("; ".join(q.get("reasons", [])) or "ผ่านการตรวจคุณภาพ")
    storage.update_run(
        run_id, status=status, finished_at=datetime.utcnow(),
        rows_loaded=outcome.get("loaded", 0), rows_rejected=outcome.get("rejected", 0),
        quality_passed=q.get("passed"), note=note,
    )


# ---------------------------------------------------------------- DAG
with DAG(
    dag_id="book_price_pipeline",
    description="รวมราคาหนังสือคอมพิวเตอร์จาก Se-ed / Naiin",
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Bangkok"),
    schedule="0 6 * * *",
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "student", "retries": 0},
    tags=["02739452", "books", "scraping"],
    doc_md=__doc__,
) as dag:
    init = init_run()

    with TaskGroup(group_id="scrape") as scrape:  # ทุกแหล่งรันขนานกัน
        for src in SOURCES:
            with TaskGroup(group_id=src):
                raw = extract(src)
                transform(src, raw)

    staged = stage_data()
    qc = quality_check()
    ok_path = promote_valid()
    bad_path = quarantine_batch()
    done = finalize()

    init >> scrape >> staged >> qc >> [ok_path, bad_path] >> done
