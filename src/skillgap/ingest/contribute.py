"""S1 用户贡献通道（Tier B，中国市场主通道；DATA_GOVERNANCE §3）。

opt-in（默认不贡献）→ PII 检测/脱敏 → 去重 → 质检 → 入库（consent=market_analysis）。
deletion_code 明文仅一次性返回，库中只存哈希（防探测）。
"""
from __future__ import annotations

import hashlib
import json
import secrets
import string
from datetime import datetime, timezone

import psycopg

from skillgap.ingest.normalize import content_hash
from skillgap.ingest.pii import detect_pii, redact
from skillgap.ingest.pipeline import process_record
from skillgap.ingest.quality import validate_jd
from skillgap.models import RawRecord, SourceFields

_ALPHABET = string.ascii_uppercase + string.digits


class QuarantinedContribution(RuntimeError):
    pass


class ConsentRequired(ValueError):
    pass


class ContributeResult:
    def __init__(self, job_id: int | None, deduplicated: bool,
                 pii_redaction: dict | None, deletion_code: str | None):
        self.job_id = job_id
        self.deduplicated = deduplicated
        self.pii_redaction = pii_redaction
        self.deletion_code = deletion_code


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def contribute_jd(conn: psycopg.Connection, jd_text: str, consent: bool,
                  title: str, source_hint: str = "other") -> ContributeResult:
    """source_hint 仅作来源统计标签（API §2.2）；系统不向任何平台发请求。"""
    if not consent:
        raise ConsentRequired("consent=false：未经同意不入库（B1 口径）")

    # S4/S5（G3 门禁：贡献通道强制）
    findings = detect_pii(jd_text)
    redacted, report = redact(jd_text, findings)

    # S6 预检去重（process_record 内有 DB 唯一约束兜底）
    chash = content_hash(redacted)
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM job WHERE content_hash = %s", (chash,))
        existing = cur.fetchone()
    if existing:
        return ContributeResult(existing["id"], True, report, None)

    # S7 质检（隔离 → 抛错并留 raw 复核队列）
    verdict = validate_jd(title, redacted)
    if verdict.verdict != "pass":
        rec = _to_record(redacted, title)
        _stage_quarantined(conn, rec, verdict.reasons)
        raise QuarantinedContribution(
            f"贡献进入人工复核队列（quarantine；原因: {verdict.reasons}）")

    rec = _to_record(redacted, title)
    outcome, _meta = process_record(conn, rec)
    if outcome.status in ("quarantined", "rejected"):
        raise QuarantinedContribution(f"贡献被拒绝（{outcome.reasons}）")
    if outcome.status == "error" or outcome.job_id is None:
        raise RuntimeError(f"贡献入库失败: {outcome.status} {outcome.reasons}")

    # source_hint：仅来源统计标签，写入 parsed_metadata
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE job SET parsed_metadata = coalesce(parsed_metadata, '{}'::jsonb)"
            " || jsonb_build_object('source_hint', %s::text) WHERE id = %s",
            (source_hint, outcome.job_id))

    # deletion_code：明文一次性返回
    code = "-".join("".join(secrets.choice(_ALPHABET) for _ in range(4))
                    for _ in range(2))
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO deletion_code (job_id, code_hash) VALUES (%s, %s)",
            (outcome.job_id, _hash_code(code)))
    conn.commit()
    return ContributeResult(outcome.job_id, False, report, code)


def _to_record(redacted_text: str, title: str) -> RawRecord:
    src = SourceFields(
        source_type="user_submitted",
        source_name="user_contribution",
        collected_at=datetime.now(timezone.utc),
        submitted_at=datetime.now(timezone.utc),
        license_or_usage_note="user opt-in anonymous contribution",
        consent_status="market_analysis",
        data_quality="auto_passed",
    )
    return RawRecord(
        title=title,
        raw_text=redacted_text,
        source=src,
    )


def _stage_quarantined(conn, rec: RawRecord, reasons: list[str]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO raw_jobs (payload, source_fields, status, error)
               VALUES (%s::jsonb, %s::jsonb, 'quarantined', %s)""",
            (rec.model_dump_json(), rec.source.model_dump_json(),
             json.dumps(reasons, ensure_ascii=False)))
    conn.commit()


def delete_contribution(conn: psycopg.Connection, code: str) -> bool:
    """凭 code 删除贡献（级联 job_skill/deletion_code）；错误一律 False（防探测）。"""
    with conn.cursor() as cur:
        cur.execute(
            """DELETE FROM job WHERE id IN (
                 SELECT job_id FROM deletion_code WHERE code_hash = %s)
               RETURNING id""",
            (_hash_code(code),))
        deleted = cur.fetchone()
    conn.commit()
    return deleted is not None
