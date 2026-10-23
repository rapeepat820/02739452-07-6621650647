"""ตรวจคุณภาพข้อมูลก่อนเข้าตารางหลัก (ไม่มี I/O)"""
from __future__ import annotations


def evaluate(rows: list[dict], max_invalid_ratio: float, min_rows: int) -> dict:
    total = len(rows)
    invalid = sum(1 for r in rows if r.get("issues"))
    ratio = invalid / total if total else 1.0
    reasons = []
    if total < min_rows:
        reasons.append(f"จำนวนแถว {total} น้อยกว่าขั้นต่ำ {min_rows}")
    if ratio > max_invalid_ratio:
        reasons.append(f"สัดส่วนแถวเสีย {ratio:.0%} เกินเกณฑ์ {max_invalid_ratio:.0%}")
    return {
        "total": total,
        "invalid": invalid,
        "invalid_ratio": round(ratio, 4),
        "passed": not reasons,
        "reasons": reasons,
    }
