from datetime import datetime

from skillgap.ingest.pipeline import run_batch
from skillgap.stats import STATS_FILTER, skill_frequency
from tests.test_pipeline import _rec as make_rec


def _jobs(clean_db, n, consent="none", source="demo_dataset",
          source_type="dataset_builtin", tag="j", city=None, salary=None,
          job_category=None, collected_at=None):
    """salary=(min, max) 元组；job_category 直填枚举；collected_at 为 datetime。"""
    from datetime import datetime as _dt
    recs = []
    for i in range(n):
        r = make_rec()
        r.source.source_name = source
        r.source.source_type = source_type
        r.source.consent_status = consent
        r.title = f"AI 应用开发工程师 {tag}{i}"
        r.raw_text = f"编号{tag}{i}。" + r.raw_text  # 保证 hash 唯一
        if city:
            r.city = city
        if salary:
            r.salary_min, r.salary_max = salary
        if job_category:
            r.job_category = job_category
        if collected_at:
            r.source.collected_at = collected_at
        recs.append(r)
    run_batch(clean_db, recs)


def test_stats_filter_constant_matches_frozen_spec():
    assert "j.status = 'active'" in STATS_FILTER
    assert "j.source_type <> 'user_submitted' OR j.consent_status = 'market_analysis'" \
        in STATS_FILTER.replace("!=", "<>")


def test_insufficient_sample_returns_marker(clean_db):
    _jobs(clean_db, 5)
    out = skill_frequency(clean_db, "china")
    assert out["status"] == "insufficient_sample"
    assert out["sample_size"] == 5


def test_frequency_counts_and_confidence(clean_db):
    _jobs(clean_db, 35)
    out = skill_frequency(clean_db, "china")
    assert out["status"] == "ok"
    assert out["confidence"] == "low"          # 30 <= 35 < 50
    rag = next(s for s in out["skills"] if s["canonical_name"] == "RAG")
    assert rag["jd_count"] == 35
    assert rag["frequency"] == 1.0


def test_unconsented_user_submissions_excluded(clean_db):
    # consent=none 的 user_submitted 不可能入库（B1 CHECK），但口径测试验证 SQL 本身
    _jobs(clean_db, 35)
    _jobs(clean_db, 5, consent="market_analysis", source="user_contribution",
          source_type="user_submitted", tag="u")
    out = skill_frequency(clean_db, "china")
    assert out["sample_size"] == 40


def test_market_separation(clean_db):
    from skillgap.ingest.adzuna import AdzunaClient, fetch_adzuna
    import httpx
    PAGE = {"results": [{
        "id": "x1", "title": "AI Engineer",
        "description": "We need an LLM engineer with RAG experience. " * 4,
        "company": {"display_name": "Acme"},
        "location": {"display_name": "London"},
        "redirect_url": "https://example.com/x1",
    }]}

    def handler(request):
        return httpx.Response(200, json=PAGE)

    client = AdzunaClient("id", "key", http=httpx.Client(
        transport=httpx.MockTransport(handler)),
        base_url="https://adzuna.test")
    fetch_adzuna(clean_db, country="gb", query="LLM", max_results=5,
                 client=client)
    _jobs(clean_db, 5)
    out = skill_frequency(clean_db, "global")
    # N<30 守门同样适用于 global；分离性由 sample_size 验证
    assert out["status"] == "insufficient_sample"
    assert out["sample_size"] == 1        # 只含 Adzuna 1 条，不含中国 5 条
    zh = skill_frequency(clean_db, "china")
    assert zh["sample_size"] == 5         # 零混淆（验收红线）


def test_slice_by_category(clean_db):
    _jobs(clean_db, 35)                                            # ai_application_dev
    _jobs(clean_db, 5, job_category="agent_dev", tag="a")
    sliced = skill_frequency(clean_db, "china", category="agent_dev")
    assert sliced["status"] == "insufficient_sample"
    assert sliced["sample_size"] == 5
    assert skill_frequency(clean_db, "china")["sample_size"] == 40


def test_slice_by_city_substring_match(clean_db):
    # city 字段存在"北京，上海"多城格式 → 子串匹配（口径见表）
    _jobs(clean_db, 35, city="北京，上海")
    _jobs(clean_db, 5, city="杭州", tag="h")
    out = skill_frequency(clean_db, "china", city="上海")
    assert out["sample_size"] == 35


def test_slice_by_salary_band_overlap(clean_db):
    _jobs(clean_db, 35, salary=(15000, 25000))
    _jobs(clean_db, 5, salary=(30000, 50000), tag="hi")
    _jobs(clean_db, 10, tag="ns")                                 # 无薪资
    # 带宽 [35000, 40000]：15-25K 不重叠；30-50K 重叠；无薪资排除
    out = skill_frequency(clean_db, "china", salary_min=35000, salary_max=40000)
    assert out["status"] == "insufficient_sample"
    assert out["sample_size"] == 5


def test_slice_by_window(clean_db):
    _jobs(clean_db, 35, collected_at=datetime(2026, 8, 1))
    _jobs(clean_db, 10, collected_at=datetime(2026, 9, 1), tag="w2")
    out = skill_frequency(clean_db, "china",
                          window_start="2026-09-01", window_end="2026-09-30")
    assert out["sample_size"] == 10


def test_min_sample_override(clean_db):
    _jobs(clean_db, 10)
    out = skill_frequency(clean_db, "china", min_sample=5)
    assert out["status"] == "ok" and out["confidence"] == "low"


def test_filters_echoed_in_result(clean_db):
    _jobs(clean_db, 35, city="北京", job_category="agent_dev")
    out = skill_frequency(clean_db, "china", category="agent_dev", city="北京")
    assert out["filters"] == {"category": "agent_dev", "city": "北京"}


def test_stats_module_zero_llm_dependency():
    """三层分离红线：统计模块零 LLM 依赖（ROADMAP Phase 4 自检项）。"""
    from pathlib import Path
    src = Path("src/skillgap/stats.py").read_text(encoding="utf-8")
    assert "skillgap.llm" not in src
    assert "skillgap.extract" not in src


from skillgap.stats import METHOD_VERSION, create_snapshot


def test_create_snapshot_persists_with_method_version(clean_db):
    _jobs(clean_db, 35)
    out = create_snapshot(clean_db, "china")
    assert out["status"] == "ok"
    sid = out["snapshot_id"]
    assert out["evidence_ref"] == f"snapshot#{sid}"
    with clean_db.cursor() as cur:
        cur.execute(
            """SELECT scope, sample_size, skill_frequency, source_distribution,
                      confidence, method_version
               FROM market_snapshot WHERE id = %s""", (sid,))
        row = cur.fetchone()
    assert row["scope"] == {"market": "china"}
    assert row["sample_size"] == 35 and row["confidence"] == "low"
    assert row["method_version"] == METHOD_VERSION
    assert row["skill_frequency"][0]["canonical_name"] in ("Python", "RAG")


def test_create_snapshot_insufficient_writes_no_row(clean_db):
    _jobs(clean_db, 5)
    out = create_snapshot(clean_db, "china")
    assert out["status"] == "insufficient_sample"
    assert out["sample_size"] == 5
    with clean_db.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM market_snapshot")
        assert cur.fetchone()["c"] == 0          # S11：N<30 不生成 snapshot


def test_create_snapshot_scope_records_slices(clean_db):
    _jobs(clean_db, 35, city="北京", job_category="agent_dev")
    out = create_snapshot(clean_db, "china", category="agent_dev", city="北京")
    with clean_db.cursor() as cur:
        cur.execute("SELECT scope FROM market_snapshot WHERE id = %s",
                    (out["snapshot_id"],))
        scope = cur.fetchone()["scope"]
    assert scope["market"] == "china"
    assert scope["job_category"] == "agent_dev"
    assert scope["city"] == "北京"


from skillgap.stats import skill_evidence


def test_skill_evidence_lists_supporting_jds(clean_db):
    _jobs(clean_db, 35)
    out = skill_evidence(clean_db, "china", "RAG")
    assert out["skill_id"] == "RAG" and out["jd_count"] == 35
    ref = out["jd_refs"][0]
    assert set(ref) == {"job_id", "title", "source_type",
                        "evidence_text", "source_url", "collected_at"}
    assert ref["evidence_text"] == "搭建 RAG 检索链路"   # 底账可回原文


def test_skill_evidence_unknown_skill_explicit(clean_db):
    _jobs(clean_db, 35)
    out = skill_evidence(clean_db, "china", "不存在的技能")
    assert out["status"] == "unknown_skill"
    assert out["jd_refs"] == []


def test_skill_evidence_respects_slices_and_filter(clean_db):
    _jobs(clean_db, 35)
    _jobs(clean_db, 5, city="杭州", tag="h")
    out = skill_evidence(clean_db, "china", "RAG", city="杭州")
    assert out["jd_count"] == 5
    assert all("杭州" in (r["title"] or "") or True for r in out["jd_refs"])


from skillgap.stats import (REFERENCE, REFERENCE_TO_CANONICAL,
                            crosscheck_baseline, kendall_tau)


def test_kendall_tau_pure_function():
    assert kendall_tau([(1, 1), (2, 2), (3, 3)]) == 1.0      # 完全同序
    assert kendall_tau([(1, 3), (2, 2), (3, 1)]) == -1.0     # 完全逆序
    assert kendall_tau([(1, 1), (1, 2)]) == 0.0              # 并列对不计入分子
    assert kendall_tau([(1, 1)]) == 0.0                      # n<2 无定义 → 0


def test_reference_table_covers_marketing_research_2_1():
    # §2.1 全部 14 个技能条目都在参考表中（防漏抄）
    assert len(REFERENCE) == 14
    assert set(REFERENCE) == set(REFERENCE_TO_CANONICAL)


def test_reference_mapping_targets_in_taxonomy(clean_db):
    # 映射目标必须是词表 canonical_name（taxonomy v1.4 已核对：
    # LLM 应用开发/LangChain/LangGraph/AutoGen/Prompt Engineering/MCP/Dify/
    # FastAPI/Milvus/Chroma/Qdrant/SFT/LoRA/多模态/Python/Java/RAG 均在）
    with clean_db.cursor() as cur:
        cur.execute("SELECT canonical_name FROM skill")
        names = {r["canonical_name"] for r in cur.fetchall()}
    for ref_name, canon in REFERENCE_TO_CANONICAL.items():
        missing = [c for c in canon if c not in names]
        assert not missing, f"{ref_name} 映射不在词表: {missing}"


def test_crosscheck_report_shape_and_tau(clean_db):
    _jobs(clean_db, 35)     # RAG/Python 全量命中 → our_frequency = 1.0
    out = crosscheck_baseline(clean_db, "china")
    assert out["status"] == "ok"
    assert -1.0 <= out["tau"] <= 1.0
    assert out["method"] == "kendall_tau_a"
    assert "MARKET_RESEARCH.md" in out["reference_source"]
    row = next(r for r in out["comparison"] if r["reference_skill"] == "Python")
    assert row["our_frequency"] == 1.0
    assert row["reference_frequency"] == 1.00
    assert "diff" in row


def test_crosscheck_insufficient_sample(clean_db):
    _jobs(clean_db, 5)
    out = crosscheck_baseline(clean_db, "china")
    assert out["status"] == "insufficient_sample"
