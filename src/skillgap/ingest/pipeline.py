"""S2-S10 管道编排（DATA_PIPELINE §2 逐步落地；每步可独立重跑、失败隔离）。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

from skillgap.ingest.extract import (
    ManualSkillExtractor, load_alias_map, record_candidates, resolve_skill_id,
)
from skillgap.ingest.normalize import (
    content_hash, detect_language, determine_market, normalize_job_category,
    parse_salary_range,
)
from skillgap.ingest.pii import detect_pii, redact
from skillgap.ingest.quality import validate_jd
from skillgap.ingest.sources import get_source
from skillgap.models import BatchReport, RawRecord, RowError

# PII 强制通道（G3：贡献类数据入库前必过 PII；公开 Tier A 源不强制）
PII_REQUIRED_SOURCE_TYPES = {"user_submitted", "csv_import", "dataset_builtin"}


@dataclass
class RecordOutcome:
    status: Literal["inserted", "duplicate", "quarantined", "rejected",
                    "extraction_failed", "error"]
    job_id: int | None = None
    reasons: list[str] = field(default_factory=list)


def _resolve_company(conn, name: str | None) -> int | None:
    if not name:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO company (name) VALUES (%s)
               ON CONFLICT (name) DO NOTHING RETURNING id""",
            (name.strip(),))
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute("SELECT id FROM company WHERE name = %s", (name.strip(),))
        return cur.fetchone()["id"]


def _dedup_lookup(conn, chash: str) -> int | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM job WHERE content_hash = %s", (chash,))
        row = cur.fetchone()
    return row["id"] if row else None


def process_record(conn, rec: RawRecord, row_index: int = 0) -> tuple[RecordOutcome, dict]:
    """单条记录 S3→S7（+S8/S9 如有标注）→S10。返回 (outcome, 元信息)。"""
    meta: dict = {}

    src = get_source(conn, rec.source.source_name)
    # S3 规范化
    text = rec.raw_text
    language = detect_language(text)
    market = determine_market(language, src["covers_market"])
    ambiguous_market = market is None
    if market is None:
        market = "china" if "china" in src["covers_market"] else "global"
        meta["market_ambiguous"] = True

    # S4/S5 PII（仅贡献类通道强制；Adzuna 双保险：断言 market=global）
    pii_report = None
    if rec.source.source_type in PII_REQUIRED_SOURCE_TYPES:
        findings = detect_pii(text)
        text, pii_report = redact(text, findings)
        # raw 暂存 payload 必须为脱敏后载荷（DATA_GOVERNANCE §3 双轨）
        rec = rec.model_copy(update={"raw_text": text})
    if rec.source.source_type == "public_api" and market != "global":
        return RecordOutcome("rejected", reasons=["market_guard_violation"]), meta

    # S6 去重（content_hash 在脱敏后文本上计算）
    chash = content_hash(text)
    existing = _dedup_lookup(conn, chash)
    if existing is not None:
        return RecordOutcome("duplicate", job_id=existing), meta

    # S7 质检
    verdict = validate_jd(rec.title, text)
    if verdict.verdict == "reject":
        _mark_raw(conn, rec, "rejected", ",".join(verdict.reasons))
        return RecordOutcome("rejected", reasons=verdict.reasons), meta
    if verdict.verdict == "quarantine":
        _mark_raw(conn, rec, "quarantined", ",".join(verdict.reasons))
        return RecordOutcome("quarantined", reasons=verdict.reasons), meta

    # S8 抽取（手工标注通道；LLM Phase 3）
    annotations = []
    extraction_error = None
    if rec.suggested_skills:
        try:
            annotations = ManualSkillExtractor(rec.suggested_skills).extract(text)
        except ValueError as e:
            extraction_error = str(e)

    # S10 入库（事务：job + job_skill）
    job_category = normalize_job_category(rec.job_category, rec.title, text)
    salary_min, salary_max = rec.salary_min, rec.salary_max
    if salary_min is None and text:
        salary_min, salary_max = parse_salary_range(text)

    alias_map = load_alias_map(conn)
    parsed_metadata = {"market_ambiguous": ambiguous_market}
    if pii_report:
        parsed_metadata["pii_redaction"] = pii_report
    if rec.source.source_type in ("user_submitted",) and not annotations:
        parsed_metadata["extraction_status"] = "pending"  # Phase 3 LLM 回填

    status = "extraction_failed" if extraction_error else "active"
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO job (title, job_category, company_id, city, country,
                   region, market, language, salary_min, salary_max,
                   salary_currency, raw_text, status, source_id, source_type,
                   source_url, collected_at, submitted_at, content_hash,
                   consent_status, data_quality, soft_requirements,
                   parsed_metadata)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id""",
                (rec.title.strip(), job_category,
                 _resolve_company(conn, rec.company_name), rec.city, rec.country,
                 rec.region, market, language or "zh", salary_min, salary_max,
                 rec.salary_currency, text, status, src["id"],
                 rec.source.source_type, rec.source.source_url,
                 rec.source.collected_at, rec.source.submitted_at, chash,
                 rec.source.consent_status, rec.source.data_quality,
                 _jsonb(rec.soft_requirements), _jsonb(parsed_metadata)),
            )
            job_id = cur.fetchone()["id"]

            if extraction_error is None and annotations:
                unresolved: list[str] = []
                for ann in annotations:
                    skill_id = resolve_skill_id(ann.raw_name, alias_map)
                    if skill_id is None:
                        unresolved.append(ann.raw_name)
                        continue
                    cur.execute(
                        """INSERT INTO job_skill (job_id, skill_id, importance,
                           intensity, evidence_text, extracted_by)
                           VALUES (%s,%s,%s,%s,%s,'manual')
                           ON CONFLICT (job_id, skill_id) DO NOTHING""",
                        (job_id, skill_id, ann.importance, ann.intensity,
                         ann.evidence_text))
                if unresolved:
                    record_candidates(conn, unresolved, job_id)

    _mark_raw(conn, rec, "done", None)
    if extraction_error:
        return (RecordOutcome("extraction_failed", job_id=job_id,
                              reasons=[extraction_error]), meta)
    return RecordOutcome("inserted", job_id=job_id), meta


def _jsonb(value):
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _mark_raw(conn, rec: RawRecord, status: str, error: str | None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO raw_jobs (payload, source_fields, status, error, processed_at)
               VALUES (%s::jsonb, %s::jsonb, %s, %s, now())""",
            (rec.model_dump_json(), rec.source.model_dump_json(), status, error))
    conn.commit()


def run_batch(conn, records: list[RawRecord]) -> BatchReport:
    """批次入口：逐条处理（行级失败不中断整批），产出导入报告并入 ingest_batch。"""
    if not records:
        return BatchReport(source_name="(empty)")
    report = BatchReport(source_name=records[0].source.source_name)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO ingest_batch (source_name, source_type, total)
               VALUES (%s, %s, %s) RETURNING id""",
            (report.source_name, records[0].source.source_type, len(records)))
        batch_id = cur.fetchone()["id"]
    conn.commit()

    for i, rec in enumerate(records):
        report.total += 1
        try:
            outcome, _meta = process_record(conn, rec, row_index=i)
        except Exception as e:  # 行级错误：记录不中断
            report.errors.append(RowError(row=i, stage="pipeline", message=str(e)))
            conn.rollback()
            continue
        if outcome.status == "inserted":
            report.inserted += 1
        elif outcome.status == "duplicate":
            report.duplicates += 1
        elif outcome.status == "quarantined":
            report.quarantined += 1
        elif outcome.status == "rejected":
            report.rejected += 1
        elif outcome.status == "extraction_failed":
            report.extraction_failed += 1

    with conn.cursor() as cur:
        cur.execute(
            """UPDATE ingest_batch SET inserted=%s, duplicates=%s, quarantined=%s,
               rejected=%s, extraction_failed=%s, error_count=%s,
               finished_at=now(), errors=%s
               WHERE id=%s""",
            (report.inserted, report.duplicates, report.quarantined,
             report.rejected, report.extraction_failed, len(report.errors),
             _jsonb([e.model_dump() for e in report.errors]), batch_id))
    conn.commit()
    return report
