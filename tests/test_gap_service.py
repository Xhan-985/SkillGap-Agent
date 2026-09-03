"""Phase 6 服务层单测（单岗模式，真实 PG 测试库，零 LLM）。

边界用例锚定 ROADMAP Phase 6 验收：完全达标（gaps 空）/ 完全无关（全 genuine）；
transferable 判定锚定 DATA_MODEL §4.4 + skill_relations_v1.csv 种子。
"""
import pytest

from skillgap.gap.service import (
    CandidateNotFound, GapQueryError, JobNotFound, get_gaps,
)
from skillgap.profile.service import add_manual_skill, analyze_resume
from tests.profile_fixtures import EXTRACTION_A, EXTRACTION_B, FakeResumeExtractor
from tests.test_schema import _insert_job, _job_kwargs, _source


def _mk_job(clean_db, **kw):
    sid = _source(clean_db)
    kw.setdefault("content_hash", "h-gap")
    return _insert_job(clean_db, **_job_kwargs(sid, **kw))


def _req(clean_db, job_id, skill, importance, intensity=None):
    """插入 job_skill 要求行（extracted_by='manual'）。"""
    sid = clean_db.execute(
        "SELECT id FROM skill WHERE canonical_name = %s", (skill,)
    ).fetchone()["id"]
    clean_db.execute(
        """INSERT INTO job_skill
           (job_id, skill_id, importance, intensity, evidence_text, extracted_by)
           VALUES (%s, %s, %s, %s, %s, 'manual')""",
        (job_id, sid, importance, intensity, f"要求 {skill}"))
    clean_db.commit()


def _mk_candidate(clean_db, extraction, resume):
    return analyze_resume(clean_db, resume,
                          FakeResumeExtractor(extraction))["candidate_id"]


def _by_skill(gaps):
    return {g["skill_id"]: g for g in gaps}


# ---- happy path ----

def test_gap_basic_single_job(clean_db):
    """画像 A（RAG L4 / Python L3）vs RAG 熟练 + Python 精通：
    RAG 达标不进 gaps；Python gap=2，自身证据 conf 0.6 → transferable。"""
    cid = _mk_candidate(clean_db, EXTRACTION_A, "简历 A" * 30)
    jid = _mk_job(clean_db)
    _req(clean_db, jid, "RAG", "must_have", "熟练")
    _req(clean_db, jid, "Python", "must_have", "精通")
    out = get_gaps(clean_db, cid, job_id=jid)
    assert out["mode"] == "job"
    assert out["gap_version"] == "gap-v1"
    by = _by_skill(out["gaps"])
    assert set(by) == {"Python"}                 # RAG 4>=4 达标排除
    assert by["Python"]["required_level"] == 5
    assert by["Python"]["actual_level"] == 3
    assert by["Python"]["gap"] == 2
    assert by["Python"]["type"] == "transferable"
    tr = {t["skill_id"]: t for t in out["transferable"]}
    assert tr["Python"]["via"] == "Python"       # 自身证据支撑
    assert tr["Python"]["note"] == "自身已有证据但等级不足（需深化）"


def test_java_evidence_makes_python_transferable(clean_db):
    """§4.4：Java conf≥0.5 + skill_relation 种子（Java↔Python）→ Python 缺口
    判 transferable，note 取种子 note。"""
    cid = _mk_candidate(clean_db, EXTRACTION_B, "简历 B" * 30)
    add_manual_skill(clean_db, cid, "Java", 4)
    jid = _mk_job(clean_db)
    _req(clean_db, jid, "Python", "must_have", "精通")
    out = get_gaps(clean_db, cid, job_id=jid)
    g = _by_skill(out["gaps"])["Python"]
    assert g["gap"] == 5                          # Java 不计入 Python actual
    assert g["type"] == "transferable"
    tr = out["transferable"][0]
    assert tr["skill_id"] == "Python"
    assert tr["via"] == "Java"
    assert tr["note"] == "工程能力与基础编程范式可迁移"


def test_low_confidence_own_skill_is_genuine(clean_db):
    """画像 B（RAG conf=0.3）vs RAG 精通 → gap=2 且 genuine（conf<0.5）。"""
    cid = _mk_candidate(clean_db, EXTRACTION_B, "简历 B" * 30)
    jid = _mk_job(clean_db)
    _req(clean_db, jid, "RAG", "must_have", "精通")
    out = get_gaps(clean_db, cid, job_id=jid)
    g = _by_skill(out["gaps"])["RAG"]
    assert (g["gap"], g["type"]) == (2, "genuine")
    assert out["transferable"] == []


def test_fully_qualified_job_empty_gaps(clean_db):
    """边界用例（MVP 验收）：完全达标 → gaps 空。"""
    cid = _mk_candidate(clean_db, EXTRACTION_A, "简历 A" * 30)
    jid = _mk_job(clean_db)
    _req(clean_db, jid, "RAG", "must_have", "熟练")
    _req(clean_db, jid, "Python", "must_have", "熟悉")
    out = get_gaps(clean_db, cid, job_id=jid)
    assert out["gaps"] == []
    assert out["transferable"] == []


def test_unrelated_job_all_genuine(clean_db):
    """边界用例（MVP 验收）：完全无关岗位（Docker/Git，与画像零关联）→
    全 genuine、全额 gap。"""
    cid = _mk_candidate(clean_db, EXTRACTION_B, "简历 B" * 30)
    jid = _mk_job(clean_db)
    _req(clean_db, jid, "Docker", "must_have", "熟练")
    _req(clean_db, jid, "Git", "must_have", "熟悉")
    out = get_gaps(clean_db, cid, job_id=jid)
    by = _by_skill(out["gaps"])
    assert set(by) == {"Docker", "Git"}
    assert all(g["type"] == "genuine" for g in by.values())
    assert by["Docker"]["actual_level"] == 0
    assert (by["Docker"]["gap"], by["Git"]["gap"]) == (4, 3)


# ---- required_level 缺省与封顶（D1） ----

def test_null_intensity_must_have_defaults_3(clean_db):
    cid = _mk_candidate(clean_db, EXTRACTION_B, "简历 B" * 30)
    jid = _mk_job(clean_db)
    _req(clean_db, jid, "LangGraph", "must_have", None)
    out = get_gaps(clean_db, cid, job_id=jid)
    g = _by_skill(out["gaps"])["LangGraph"]
    assert g["required_level"] == 3               # 熟悉中性档


def test_nice_to_have_capped_at_2(clean_db):
    """RAG L3 vs nice_to_have 精通 → required 封顶 2 → gap 0 不进 gaps。"""
    cid = _mk_candidate(clean_db, EXTRACTION_B, "简历 B" * 30)
    jid = _mk_job(clean_db)
    _req(clean_db, jid, "RAG", "nice_to_have", "精通")
    out = get_gaps(clean_db, cid, job_id=jid)
    assert out["gaps"] == []


# ---- 错误与参数校验 ----

def test_candidate_not_found(clean_db):
    jid = _mk_job(clean_db)
    with pytest.raises(CandidateNotFound):
        get_gaps(clean_db, 999, job_id=jid)


def test_job_not_found(clean_db):
    cid = _mk_candidate(clean_db, EXTRACTION_B, "简历 B" * 30)
    with pytest.raises(JobNotFound):
        get_gaps(clean_db, cid, job_id=999)


def test_job_id_and_category_mutually_exclusive(clean_db):
    cid = _mk_candidate(clean_db, EXTRACTION_B, "简历 B" * 30)
    with pytest.raises(GapQueryError):
        get_gaps(clean_db, cid, job_id=1, category="ai_application_dev")
    with pytest.raises(GapQueryError):
        get_gaps(clean_db, cid)


# ---- demand 原料（D5：ROI 排序接口供 Phase 7/8） ----

def test_gap_rows_carry_demand_and_cost(clean_db):
    cid = _mk_candidate(clean_db, EXTRACTION_B, "简历 B" * 30)
    jid = _mk_job(clean_db)
    _req(clean_db, jid, "Docker", "must_have", "熟练")
    out = get_gaps(clean_db, cid, job_id=jid)
    g = _by_skill(out["gaps"])["Docker"]
    assert set(g["demand"]) == {"frequency", "sample_size"}
    assert 0.0 <= g["demand"]["frequency"] <= 1.0
    assert g["cost"] == "low"                      # 词表 learning_cost


def test_gaps_sorted_by_gap_desc(clean_db):
    cid = _mk_candidate(clean_db, EXTRACTION_B, "简历 B" * 30)
    jid = _mk_job(clean_db)
    _req(clean_db, jid, "Docker", "must_have", "熟悉")     # gap 3
    _req(clean_db, jid, "Git", "must_have", "精通")        # gap 5
    _req(clean_db, jid, "MySQL", "must_have", "熟练")      # gap 4
    out = get_gaps(clean_db, cid, job_id=jid)
    assert [g["skill_id"] for g in out["gaps"]] == ["Git", "MySQL", "Docker"]
    gaps = [g["gap"] for g in out["gaps"]]
    assert gaps == sorted(gaps, reverse=True)


# ---- 类目聚合模式（D4：频次 ≥ min_freq 入清单） ----

def _mk_category_jobs(clean_db, n_jobs, category="ai_application_dev"):
    """造 n 条同类目 job，返回 job id 列表（content_hash 唯一）。"""
    sid = _source(clean_db)
    ids = []
    for i in range(n_jobs):
        ids.append(_insert_job(clean_db, **_job_kwargs(
            sid, content_hash=f"h-cat-{i}", job_category=category)))
    return ids


def test_category_mode_basic(clean_db):
    """10 岗类目中 5 岗要求 Docker must 熟练 → freq 0.5 入清单；
    画像 B 无 Docker → genuine gap=4；meta 含类目样本量与快照引用。"""
    cid = _mk_candidate(clean_db, EXTRACTION_B, "简历 B" * 30)
    jids = _mk_category_jobs(clean_db, 10)
    for j in jids[:5]:
        _req(clean_db, j, "Docker", "must_have", "熟练")
    out = get_gaps(clean_db, cid, category="ai_application_dev")
    assert out["mode"] == "category"
    assert out["category_sample_size"] == 10
    g = _by_skill(out["gaps"])["Docker"]
    assert (g["required_level"], g["gap"], g["type"]) == (4, 4, "genuine")
    assert g["demand"]["frequency"] == 0.5
    assert g["demand"]["sample_size"] == 10


def test_category_min_freq_excludes_rare_skills(clean_db):
    """1/10 岗出现（freq 0.1 < 0.2）→ 不进要求清单，即使 must 精通。"""
    cid = _mk_candidate(clean_db, EXTRACTION_B, "简历 B" * 30)
    jids = _mk_category_jobs(clean_db, 10)
    _req(clean_db, jids[0], "Git", "must_have", "精通")
    out = get_gaps(clean_db, cid, category="ai_application_dev")
    assert "Git" not in _by_skill(out["gaps"])
    assert out["gaps"] == []


def test_category_min_freq_param_override(clean_db):
    """min_freq=0.6 → freq 0.5 的 Docker 也被排除。"""
    cid = _mk_candidate(clean_db, EXTRACTION_B, "简历 B" * 30)
    jids = _mk_category_jobs(clean_db, 10)
    for j in jids[:5]:
        _req(clean_db, j, "Docker", "must_have", "熟练")
    out = get_gaps(clean_db, cid, category="ai_application_dev",
                   min_freq=0.6)
    assert out["gaps"] == []


def test_category_required_takes_must_max(clean_db):
    """Docker 出现于 5 岗（熟练 + 精通）→ required 取 must 映射最大值 5。"""
    cid = _mk_candidate(clean_db, EXTRACTION_B, "简历 B" * 30)
    jids = _mk_category_jobs(clean_db, 10)
    for j in jids[:3]:
        _req(clean_db, j, "Docker", "must_have", "熟练")
    for j in jids[3:5]:
        _req(clean_db, j, "Docker", "must_have", "精通")
    out = get_gaps(clean_db, cid, category="ai_application_dev")
    assert _by_skill(out["gaps"])["Docker"]["required_level"] == 5


def test_category_no_must_rows_defaults_2(clean_db):
    """技能仅以 nice_to_have 出现 → required=2（D1 缺省档）。"""
    cid = _mk_candidate(clean_db, EXTRACTION_B, "简历 B" * 30)
    jids = _mk_category_jobs(clean_db, 10)
    for j in jids[:5]:
        _req(clean_db, j, "Docker", "nice_to_have", "精通")
    out = get_gaps(clean_db, cid, category="ai_application_dev")
    assert _by_skill(out["gaps"])["Docker"]["required_level"] == 2


def test_category_snapshot_ref_in_meta(clean_db):
    """meta.snapshot 引用该市场最新快照（demand 溯源）。"""
    cid = _mk_candidate(clean_db, EXTRACTION_B, "简历 B" * 30)
    _mk_category_jobs(clean_db, 10)
    with clean_db.cursor() as cur:
        cur.execute(
            """INSERT INTO market_snapshot
               (scope, sample_size, skill_frequency, source_distribution,
                confidence, method_version)
               VALUES ('{"market": "china"}'::jsonb, 30, '{}'::jsonb,
                       '[]'::jsonb, 'low', 's11-v1')
               RETURNING id""")
        snap_id = cur.fetchone()["id"]
    clean_db.commit()
    out = get_gaps(clean_db, cid, category="ai_application_dev")
    assert out["snapshot"]["id"] == snap_id
    assert out["snapshot"]["method_version"] == "s11-v1"


def test_category_empty_returns_no_gaps(clean_db):
    """无岗位类目 → 空清单 + sample_size=0（不崩、不臆造要求）。"""
    cid = _mk_candidate(clean_db, EXTRACTION_B, "简历 B" * 30)
    out = get_gaps(clean_db, cid, category="mcp_dev")
    assert out["gaps"] == []
    assert out["category_sample_size"] == 0
    assert out["snapshot"] is None
