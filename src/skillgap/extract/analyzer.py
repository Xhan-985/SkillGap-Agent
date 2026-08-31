"""POST /api/jd/analyze 的服务层（M1）+ Phase 2 遗留回填。

无状态即时计算，默认不落库（API.md §2.1 B1 修复）；market/language/job_category
由确定性规则计算（normalize.py），LLM 只负责 skills + soft_requirements
（三层分离：LLM 不做统计、不改数值）。
"""
from __future__ import annotations

import time

import psycopg

from skillgap.extract.llm_extractor import (
    ExtractionFailed, LLMSkillExtractor,
)
from skillgap.ingest.extract import (
    alias_map_from_db, record_candidates, resolve_skill_id,
)
from skillgap.ingest.normalize import classify_job_category, detect_language
from skillgap.llm.provider import LLMError
from skillgap.models import JDExtraction

MIN_LEN, MAX_LEN = 50, 20000   # 与 quality.py 口径一致


class JDValidationError(ValueError):
    pass


def analyze_jd(conn: psycopg.Connection, jd_text: str,
               extractor: LLMSkillExtractor, title: str = "") -> dict:
    text = jd_text.strip()
    if not (MIN_LEN <= len(text) <= MAX_LEN):
        raise JDValidationError(
            f"jd_text 长度 {len(text)} 不在 [{MIN_LEN}, {MAX_LEN}]")
    language = detect_language(text)
    started = time.monotonic()
    extraction: JDExtraction = extractor.extract_full(text)
    latency_ms = int((time.monotonic() - started) * 1000)
    core = [s for s in extraction.skills if s.importance == "must_have"]
    secondary = [s for s in extraction.skills
                 if s.importance == "nice_to_have"]
    return {
        "job": {
            "title": title.strip(),
            "job_category": classify_job_category(title, text),
            "city": None,
            "market": "china" if language == "zh" else "global",
            "language": language,
        },
        "core_skills": [s.model_dump() for s in core],
        "secondary_skills": [s.model_dump() for s in secondary],
        "soft_requirements": [r.model_dump() for r in
                              extraction.soft_requirements],
        "extraction_meta": {
            "model": extractor.last_usage.get("model", ""),
            "prompt_version": extractor.gateway.prompt_version,
            "latency_ms": latency_ms,
            "total_tokens": extractor.last_usage.get("total_tokens", 0),
            "skill_count": len(extraction.skills),
        },
    }


def backfill_pending(conn: psycopg.Connection, extractor,
                     limit: int = 100) -> int:
    """回填 extraction_status=pending 的 job（Phase 2 移交项）。

    失败明示：单条 ExtractionFailed 跳过保持 pending（汇总数差值即失败数），
    不静默；词表外技能进 new_skill_candidate（周级裁决）。
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, raw_text FROM job
               WHERE parsed_metadata->>'extraction_status' = 'pending'
               ORDER BY id LIMIT %s""", (limit,))
        rows = cur.fetchall()
    amap = alias_map_from_db(conn)
    done = 0
    for row in rows:
        try:
            anns = extractor.extract(row["raw_text"])
        except (ExtractionFailed, LLMError):
            continue
        unresolved: list[str] = []
        with conn.cursor() as cur:
            for a in anns:
                sid = resolve_skill_id(a.raw_name, amap)
                if sid is None:
                    unresolved.append(a.raw_name)
                    continue
                cur.execute(
                    """INSERT INTO job_skill (job_id, skill_id, importance,
                       intensity, evidence_text, extracted_by)
                       VALUES (%s, %s, %s, %s, %s, 'llm')
                       ON CONFLICT (job_id, skill_id) DO NOTHING""",
                    (row["id"], sid, a.importance, a.intensity,
                     a.evidence_text))
            if unresolved:
                record_candidates(conn, unresolved, row["id"])
            cur.execute(
                """UPDATE job SET parsed_metadata =
                   parsed_metadata - 'extraction_status' WHERE id = %s""",
                (row["id"],))
        conn.commit()
        done += 1
    return done
