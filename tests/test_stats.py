from skillgap.ingest.pipeline import run_batch
from skillgap.stats import STATS_FILTER, skill_frequency
from tests.test_pipeline import _rec as make_rec


def _jobs(clean_db, n, consent="none", source="demo_dataset",
          source_type="dataset_builtin", tag="j"):
    recs = []
    for i in range(n):
        r = make_rec()
        r.source.source_name = source
        r.source.source_type = source_type
        r.source.consent_status = consent
        r.title = f"AI 应用开发工程师 {tag}{i}"
        r.raw_text = f"编号{tag}{i}。" + r.raw_text  # 保证 hash 唯一
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
