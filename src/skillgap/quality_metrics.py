"""E5 数据质量指标（EVALUATION_PLAN §5：五指标 + 批次报告 + 全库扫描）。"""
from __future__ import annotations

from datetime import datetime, timezone

import psycopg

from skillgap.ingest.pii import PII_RULES_VERSION
from skillgap.models import BatchReport

# 阈值（Pass / Warn / Block）——EVALUATION_PLAN §5.1
THRESHOLDS = {
    "duplicate_rate": (0.10, 0.25),
    "missing_field_rate": (0.0, 0.0),
    "invalid_jd_rate": (0.05, 0.15),
    "skill_extraction_error_rate": (0.03, 0.08),
}


def _rate(n: int, d: int) -> float:
    return round(n / d, 4) if d else 0.0


def batch_metrics(report: BatchReport) -> dict:
    """批次指标：duplicate / invalid_jd / skill_extraction_error rate。"""
    extraction_attempts = report.inserted + report.extraction_failed
    return {
        "duplicate_rate": _rate(report.duplicates, report.total),
        "invalid_jd_rate": _rate(report.quarantined + report.rejected,
                                 report.total),
        "skill_extraction_error_rate": _rate(report.extraction_failed,
                                             extraction_attempts),
    }


def full_scan(conn: psycopg.Connection) -> dict:
    """全库扫描：missing_field_rate（DB 约束兜底应为 0）+ PII 命中聚合。"""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM job")
        total = cur.fetchone()["c"]
        # 来源九字段空值检查（NOT NULL 约束兜底；此处为 E5 显式口径）
        cur.execute(
            """SELECT count(*) AS c FROM job WHERE
               title IS NULL OR raw_text IS NULL OR source_id IS NULL OR
               source_type IS NULL OR collected_at IS NULL OR
               content_hash IS NULL OR data_quality IS NULL OR
               (source_type = 'public_job_page' AND source_url IS NULL) OR
               (source_type = 'user_submitted' AND consent_status IS NULL)""")
        missing = cur.fetchone()["c"]
        cur.execute(
            """SELECT count(*) AS c FROM job
               WHERE parsed_metadata ? 'pii_redaction'""")
        scan_count = cur.fetchone()["c"]
        cur.execute(
            """SELECT coalesce(sum((parsed_metadata->'pii_redaction'->'hits'
               ->> 'phone')::int), 0)
               + coalesce(sum((parsed_metadata->'pii_redaction'->'hits'
               ->> 'email')::int), 0)
               + coalesce(sum((parsed_metadata->'pii_redaction'->'hits'
               ->> 'wechat')::int), 0)
               + coalesce(sum((parsed_metadata->'pii_redaction'->'hits'
               ->> 'qq')::int), 0)
               + coalesce(sum((parsed_metadata->'pii_redaction'->'hits'
               ->> 'contact')::int), 0)
               + coalesce(sum((parsed_metadata->'pii_redaction'->'hits'
               ->> 'id_card')::int), 0) AS c
               FROM job WHERE parsed_metadata ? 'pii_redaction'""")
        hits = cur.fetchone()["c"]
    return {
        "job_count": total,
        "missing_field_rate": _rate(missing, total),
        "pii_rules_version": PII_RULES_VERSION,
        "pii_scan_count": scan_count,
        "pii_hit_total": hits if hits is not None else 0,
    }


def quality_report(conn: psycopg.Connection) -> dict:
    """聚合视图（对齐 API §2.13 响应结构；manual_audit 由人工流程回填）。"""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT count(*) AS c FROM ingest_batch
               WHERE started_at::date = CURRENT_DATE""")
        batches_today = cur.fetchone()["c"]
    scan = full_scan(conn)
    return {
        "batches_today": batches_today,
        **scan,
        "pii_detection": {
            "rules_version": scan["pii_rules_version"],
            "scan_count": scan["pii_scan_count"],
            "hit_total": scan["pii_hit_total"],
            "manual_audit_pass": None,   # 人工抽查后回填（E5 §5.1 每月抽样）
        },
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
