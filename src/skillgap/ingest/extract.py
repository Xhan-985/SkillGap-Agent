"""S8 抽取接口（SkillExtractor 协议）+ S9 归一（查表，无 LLM）。

LLM 实现属 Phase 3（LLM Gateway）；本阶段 ManualSkillExtractor
承载 Demo Dataset 的人工标注技能（extracted_by='manual'）。
"""
from __future__ import annotations

from typing import Protocol

from skillgap.ingest.normalize import canonicalize_for_hash
from skillgap.models import SkillAnnotation


class SkillExtractor(Protocol):
    def extract(self, jd_text: str) -> list[SkillAnnotation]: ...


class ManualSkillExtractor:
    """S8 手工标注通道：技能来自导入文件的 suggested_skills。"""

    def __init__(self, annotations: list[SkillAnnotation]):
        self._annotations = annotations

    def extract(self, jd_text: str) -> list[SkillAnnotation]:
        # 证据必须可在原文定位（S8 纪律：不可定位即判失败）
        for ann in self._annotations:
            if not locate_evidence(jd_text, ann.evidence_text):
                raise ValueError(
                    f"证据片段无法在 JD 原文定位: {ann.evidence_text!r}")
        return self._annotations


def locate_evidence(jd_text: str, evidence_text: str) -> bool:
    """字符串定位校验（规范化比较，容忍全角/空白/大小写差异）。"""
    return canonicalize_for_hash(evidence_text) in canonicalize_for_hash(jd_text)


def load_alias_map(conn) -> dict[str, int]:
    """alias（含 canonical_name 自身，规范化键）→ skill_id。"""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT a.alias AS key, a.skill_id AS sid FROM skill_alias a
               UNION SELECT s.canonical_name, s.id FROM skill s""")
        rows = cur.fetchall()
    return {canonicalize_for_hash(r["key"]): r["sid"] for r in rows}


alias_map_from_db = load_alias_map  # 兼容命名


def resolve_skill_id(raw_name: str, alias_map: dict[str, int]) -> int | None:
    return alias_map.get(canonicalize_for_hash(raw_name))


def record_candidates(conn, raw_names: list[str], job_id: int) -> int:
    """S9：无法归一 → new_skill_candidate（不丢弃、不静默入表）。"""
    inserted = 0
    with conn.cursor() as cur:
        for name in raw_names:
            cur.execute(
                """INSERT INTO new_skill_candidate (raw_name, first_seen_job_id)
                   VALUES (%s, %s) ON CONFLICT (raw_name) DO NOTHING""",
                (name, job_id))
            inserted += cur.rowcount
    return inserted
