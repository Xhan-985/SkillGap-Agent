"""Phase 8 recommend 服务层单测（真实 PG；零模型调用）。"""
import pytest

from skillgap.recommend.roi import ROI_VERSION
from skillgap.recommend.service import (
    CandidateNotFound, RECOMMEND_INSUFFICIENT_DATA, RecommendError, recommend,
)
from tests.test_recommend_service_fixtures import (
    seed_market, write_templates,
)


# ---- happy path ----

def test_recommend_basic(clean_db, tmp_path):
    cid = seed_market(clean_db)
    out = recommend(clean_db, cid, time_budget_days=14,
                    templates_path=write_templates(tmp_path))
    assert out["candidate_id"] == cid
    assert out["formula_version"] == ROI_VERSION
    assert out["time_budget_days"] == 14
    items = out["priority_items"]
    assert len(items) >= 1
    # MCP（freq 0.5, required 5, gap 5）vs Docker（freq 0.5, required 3,
    # gap 3）：potential_gain 按学习成本分档（见词表实际值），MCP 缺口大
    # 通常居首——但断言只锁"缺口技能入清单 + 达标技能不入"
    skills = {x["skill"] for x in items}
    assert {"MCP", "Docker"} <= skills
    # 已达标（gap=0）不入清单：RAG L4 ≥ required 3；Python L3 ≥ required 3
    assert "RAG" not in skills and "Python" not in skills
    assert items[0]["rationale"]                    # 模板已渲染


def test_recommend_snapshot_evidence_ref(clean_db, tmp_path):
    """demand 溯源：引用最新 snapshot（C4）。"""
    from psycopg.types.json import Json

    cid = seed_market(clean_db)
    # 测试库未跑 stats——手工建一个 china 快照（sample_size 需 ≥30 过守门）
    with clean_db.cursor() as cur:
        cur.execute(
            """INSERT INTO market_snapshot
               (scope, sample_size, skill_frequency, source_distribution,
                confidence, method_version)
               VALUES (%s, 32, '{}', '{}', 'high', 'stats-v1')""",
            (Json({"market": "china"}),))
    clean_db.commit()
    out = recommend(clean_db, cid,
                    templates_path=write_templates(tmp_path))
    ref = out["priority_items"][0]["evidence_ref"]
    assert ref and ref.get("snapshot_id")
    assert ref.get("sample_size") >= 30


def test_recommend_project_suggestions(clean_db, tmp_path):
    """模板匹配：交集 ≥1 + est_days ≤ budget + 交集大者先 + source 必填。"""
    cid = seed_market(clean_db)
    out = recommend(clean_db, cid, time_budget_days=14,
                    templates_path=write_templates(tmp_path))
    sugg = out["project_suggestions"]
    assert len(sugg) >= 1
    first = sugg[0]
    assert first["matched_skills"]            # 至少 1 个交集技能
    assert first["est_days"] <= 14
    assert first["source"]                    # D4：来源必填
    assert first["rationale"]


def test_recommend_budget_filters_long_projects(clean_db, tmp_path):
    """budget=7：est_days>7 的模板被过滤。"""
    cid = seed_market(clean_db)
    out = recommend(clean_db, cid, time_budget_days=7,
                    templates_path=write_templates(tmp_path))
    assert all(s["est_days"] <= 7 for s in out["project_suggestions"])


def test_recommend_persists(clean_db, tmp_path):
    """recommendation 落库断言。"""
    cid = seed_market(clean_db)
    out = recommend(clean_db, cid,
                    templates_path=write_templates(tmp_path))
    row = clean_db.execute(
        """SELECT priority_items, potential_gain, time_budget_days
           FROM recommendation WHERE candidate_id = %s
           ORDER BY id DESC LIMIT 1""", (cid,)).fetchone()
    assert row is not None
    assert row["time_budget_days"] == 14
    assert float(row["potential_gain"]) == \
        out["priority_items"][0]["potential_gain"]
    assert row["priority_items"][0]["skill"] == \
        out["priority_items"][0]["skill"]


def test_recommend_budget_persisted_per_call(clean_db, tmp_path):
    """不同预算分别落行（历史留痕）。"""
    cid = seed_market(clean_db)
    tp = write_templates(tmp_path)
    recommend(clean_db, cid, time_budget_days=7, templates_path=tp)
    recommend(clean_db, cid, time_budget_days=30, templates_path=tp)
    rows = clean_db.execute(
        "SELECT time_budget_days FROM recommendation WHERE candidate_id=%s "
        "ORDER BY id", (cid,)).fetchall()
    assert [r["time_budget_days"] for r in rows] == [7, 30]


# ---- 边界 ----

def test_recommend_candidate_not_found(clean_db, tmp_path):
    seed_market(clean_db)
    with pytest.raises(CandidateNotFound):
        recommend(clean_db, 999,
                  templates_path=write_templates(tmp_path))


def test_recommend_insufficient_market(clean_db, tmp_path):
    """市场岗 <30 → RECOMMEND_INSUFFICIENT_DATA（C4：不臆造）。"""
    cid = seed_market(clean_db)
    with pytest.raises(RecommendError) as ei:
        recommend(clean_db, cid, market="us",
                 templates_path=write_templates(tmp_path))
    assert RECOMMEND_INSUFFICIENT_DATA in str(ei.value)


def test_recommend_no_gaps(clean_db, tmp_path):
    """画像全覆盖市场要求 → 空优先级 + 空建议（不是错误）。"""
    from tests.test_recommend_service_fixtures import _FULL_PROFILE
    cid = seed_market(clean_db, profile=_FULL_PROFILE)
    out = recommend(clean_db, cid,
                    templates_path=write_templates(tmp_path))
    assert out["priority_items"] == []
    assert out["project_suggestions"] == []
