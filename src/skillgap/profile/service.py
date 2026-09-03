"""Candidate Profile 服务层（Phase 5，API §2.5-2.7）。

决策记录（docs/WEIGHT_RULES.md §4 / DECISION_LOG）：
- D1 重分析替换式：删该 candidate 全部 resume_text 行后插入新结果；
  manual 行永不删，冲突技能跳过插入 + notice（manual_overridden）。
- D2 evidence_ref="resume#L<n>" 仅分析会话内计算，不落库（原文不存）。
- D5 add_manual_skill 整行替换为 manual（confidence=1.0）；
  词表外技能拒绝（new_skill_candidate 是 LLM 新词裁决通道，非用户输入通道）。

事务性：analyze_resume 全程单事务，中途异常 rollback 不残留。
"""
from __future__ import annotations

import json
from typing import Protocol

from psycopg.types.json import Json

from skillgap.ingest.extract import (
    load_alias_map, record_candidates, resolve_skill_id,
)
from skillgap.models import ResumeExtraction, ResumeSkillAnnotation
from skillgap.profile.confidence import (
    EVIDENCE_WEIGHTS, compute_confidence,
)

RESUME_MIN_LEN = 50
RESUME_MAX_LEN = 20000


class CandidateNotFound(LookupError):
    """candidate_id 不存在。"""


class ResumeValidationError(ValueError):
    """简历文本长度/内容不合法。"""


class ManualSkillError(ValueError):
    """手动勾选不合法（词表外技能 / level 越界）。"""


class ResumeExtractor(Protocol):
    def extract_full(self, resume_text: str) -> ResumeExtraction: ...


def analyze_resume(conn, resume_text: str, extractor: ResumeExtractor,
                   candidate_id: int | None = None) -> dict:
    """简历 → 证据化画像（API §2.5）。新用户自动创建 candidate。"""
    if not (RESUME_MIN_LEN <= len(resume_text.strip()) <= RESUME_MAX_LEN):
        raise ResumeValidationError(
            f"简历长度 {len(resume_text.strip())} 不在 "
            f"[{RESUME_MIN_LEN}, {RESUME_MAX_LEN}] 区间")

    result = extractor.extract_full(resume_text)

    try:
        with conn.cursor() as cur:
            candidate_id = _ensure_candidate(cur, candidate_id)
            # D1 替换式：清掉旧 resume_text 行（证据级联删除），manual 保留
            cur.execute(
                """DELETE FROM candidate_skill
                   WHERE candidate_id = %s AND source_type = 'resume_text'""",
                (candidate_id,))
            manual_skills = _manual_skill_names(cur, candidate_id)

            alias_map = load_alias_map(conn)
            unresolved: list[str] = []
            manual_overridden: list[str] = []
            merged_duplicates: list[str] = []
            # LLM 可能产出多个 raw_name 归一到同一 skill（e2e 捕获：
            # "RAG"与"RAG 检索"同 skill_id 触发 UNIQUE 冲突）——按 skill_id
            # 合并：证据累积、level 取最大（最有利的能力宣称）
            by_skill: dict[int, list] = {}
            level_by_skill: dict[int, int] = {}
            name_by_skill: dict[int, str] = {}
            for ann in result.skills:
                skill_id = resolve_skill_id(ann.raw_name, alias_map)
                if skill_id is None:
                    unresolved.append(ann.raw_name)
                    continue
                if skill_id in manual_skills:      # D1 冲突跳过
                    manual_overridden.append(ann.raw_name)
                    continue
                if skill_id in by_skill:
                    merged_duplicates.append(ann.raw_name)
                    existing = {e.text for e in by_skill[skill_id]}
                    by_skill[skill_id].extend(
                        e for e in ann.evidences
                        if e.text not in existing)   # 同段原文不重复计（不论 type）
                    level_by_skill[skill_id] = max(
                        level_by_skill[skill_id], ann.level)
                else:
                    by_skill[skill_id] = list(ann.evidences)
                    level_by_skill[skill_id] = ann.level
                    name_by_skill[skill_id] = ann.raw_name
            skills_out = []
            for skill_id, evidences in by_skill.items():
                skills_out.append(_insert_skill(
                    cur, candidate_id, skill_id,
                    ResumeSkillAnnotation(
                        raw_name=name_by_skill[skill_id],
                        level=level_by_skill[skill_id],
                        evidences=evidences),
                    resume_text, source_type="resume_text"))
            if unresolved:
                record_candidates(conn, unresolved, None)
            soft_profile = _soft_profile_json(result)
            cur.execute(
                "UPDATE candidate SET soft_profile = %s, "
                "last_active = now() WHERE id = %s",
                (Json(soft_profile), candidate_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "candidate_id": candidate_id,
        "skills": skills_out,
        "soft_profile": soft_profile,
        "notices": {"unresolved": unresolved,
                    "manual_overridden": manual_overridden,
                    "merged_duplicates": merged_duplicates},
    }


def get_profile(conn, candidate_id: int) -> dict:
    """画像 + 每技能证据链（API §2.6；evidence_ref=null——D2 不落库）。"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT soft_profile FROM candidate WHERE id = %s",
            (candidate_id,))
        row = cur.fetchone()
        if row is None:
            raise CandidateNotFound(f"candidate {candidate_id} 不存在")
        cur.execute(
            """SELECT cs.id, s.canonical_name AS skill_id, cs.level,
                      cs.confidence, cs.source_type
               FROM candidate_skill cs JOIN skill s ON s.id = cs.skill_id
               WHERE cs.candidate_id = %s ORDER BY cs.id""",
            (candidate_id,))
        skill_rows = cur.fetchall()
        skills = []
        for r in skill_rows:
            cur.execute(
                """SELECT evidence_type, evidence_text, weight
                   FROM candidate_evidence WHERE candidate_skill_id = %s
                   ORDER BY weight DESC, id""",
                (r["id"],))
            evidences = [{"type": e["evidence_type"], "text": e["evidence_text"],
                          "weight": float(e["weight"]), "evidence_ref": None}
                         for e in cur.fetchall()]
            skills.append({
                "skill_id": r["skill_id"], "level": r["level"],
                "confidence": float(r["confidence"]),
                "source_type": r["source_type"],
                "evidences": evidences, "evidence_ref": None,
            })
    return {"candidate_id": candidate_id, "skills": skills,
            "soft_profile": row["soft_profile"]}


def add_manual_skill(conn, candidate_id: int, skill_name: str, level: int,
                     evidence_text: str | None = None) -> dict:
    """手动勾选（D5）：整行替换为 manual（confidence=1.0）。"""
    if not 1 <= level <= 5:
        raise ManualSkillError(f"level 必须在 1-5，收到 {level}")
    alias_map = load_alias_map(conn)
    skill_id = resolve_skill_id(skill_name, alias_map)
    if skill_id is None:
        raise ManualSkillError(
            f"技能 {skill_name!r} 不在词表——手动勾选仅接受词表内技能")
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM candidate WHERE id = %s", (candidate_id,))
            if cur.fetchone() is None:
                raise CandidateNotFound(f"candidate {candidate_id} 不存在")
            cur.execute(
                "DELETE FROM candidate_skill WHERE candidate_id = %s "
                "AND skill_id = %s", (candidate_id, skill_id))
            cur.execute(
                """INSERT INTO candidate_skill
                   (candidate_id, skill_id, level, confidence, source_type)
                   VALUES (%s, %s, %s, 1.0, 'manual') RETURNING id""",
                (candidate_id, skill_id, level))
            cs_id = cur.fetchone()["id"]
            cur.execute(
                """INSERT INTO candidate_evidence
                   (candidate_skill_id, evidence_type, evidence_text, weight)
                   VALUES (%s, 'manual', %s, 1.0)""",
                (cs_id, evidence_text or "手动勾选"))
            cur.execute(
                "UPDATE candidate SET last_active = now() WHERE id = %s",
                (candidate_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"candidate_id": candidate_id,
            "skill_id": _canonical_name(conn, skill_id),
            "level": level, "confidence": 1.0, "source_type": "manual"}


def delete_candidate(conn, candidate_id: int) -> bool:
    """级联删除画像/证据/匹配结果（API §2.7）。不存在 → False。"""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM candidate WHERE id = %s", (candidate_id,))
        deleted = cur.rowcount
    conn.commit()
    return deleted > 0


# ---- 内部 ----

def _ensure_candidate(cur, candidate_id: int | None) -> int:
    if candidate_id is None:
        cur.execute(
            "INSERT INTO candidate (soft_profile) VALUES (NULL::jsonb) "
            "RETURNING id")
        return cur.fetchone()["id"]
    cur.execute("SELECT id FROM candidate WHERE id = %s", (candidate_id,))
    row = cur.fetchone()
    if row is None:
        raise CandidateNotFound(f"candidate {candidate_id} 不存在")
    return row["id"]


def _manual_skill_names(cur, candidate_id: int) -> set[int]:
    cur.execute(
        "SELECT skill_id FROM candidate_skill "
        "WHERE candidate_id = %s AND source_type = 'manual'",
        (candidate_id,))
    return {r["skill_id"] for r in cur.fetchall()}


def _insert_skill(cur, candidate_id: int, skill_id: int,
                  ann: ResumeSkillAnnotation, resume_text: str,
                  source_type: str) -> dict:
    weights = [EVIDENCE_WEIGHTS[ev.type] for ev in ann.evidences]
    confidence = compute_confidence(weights)
    cur.execute(
        """INSERT INTO candidate_skill
           (candidate_id, skill_id, level, confidence, source_type)
           VALUES (%s, %s, %s, %s, %s) RETURNING id, (
               SELECT canonical_name FROM skill WHERE id = %s) AS name""",
        (candidate_id, skill_id, ann.level, confidence, source_type,
         skill_id))
    row = cur.fetchone()
    evidences = []
    for ev in ann.evidences:
        cur.execute(
            """INSERT INTO candidate_evidence
               (candidate_skill_id, evidence_type, evidence_text, weight)
               VALUES (%s, %s, %s, %s)""",
            (row["id"], ev.type, ev.text, EVIDENCE_WEIGHTS[ev.type]))
        evidences.append({"type": ev.type, "text": ev.text,
                          "weight": EVIDENCE_WEIGHTS[ev.type],
                          "evidence_ref": _line_ref(resume_text, ev.text)})
    return {"skill_id": row["name"], "level": ann.level,
            "confidence": confidence, "evidences": evidences}


def _line_ref(resume_text: str, evidence_text: str) -> str:
    """D2：证据所在 1-based 行号（规范化比较，尽力而为）。"""
    from skillgap.ingest.normalize import canonicalize_for_hash
    target = canonicalize_for_hash(evidence_text)
    for i, line in enumerate(resume_text.splitlines(), start=1):
        if target in canonicalize_for_hash(line):
            return f"resume#L{i}"
    return "resume#L?"


def _soft_profile_json(result: ResumeExtraction):
    sp = result.soft_profile
    out = {}
    for field in ("experience_years", "education", "languages"):
        v = getattr(sp, field)
        out[field] = (None if v is None
                      else {"value": v.value, "evidence_text": v.evidence_text})
    return json.loads(json.dumps(out, ensure_ascii=False))


def _canonical_name(conn, skill_id: int) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT canonical_name FROM skill WHERE id = %s", (skill_id,))
        return cur.fetchone()["canonical_name"]
