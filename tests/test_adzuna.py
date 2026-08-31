import httpx
import pytest

from skillgap.ingest import adzuna
from skillgap.ingest.adzuna import (
    ADZUNA_ATTRIBUTION, AdzunaClient, check_daily_quota, fetch_adzuna,
)
from skillgap.ingest.pipeline import run_batch  # noqa: F401 (确保模块可用)

PAGE = {
    "count": 60, "mean": 0.0, "results": [
        {
            "id": "a1b2c3", "title": "AI Engineer",
            "description": "We need an LLM engineer with RAG experience and "
                           "strong Python skills. " * 5,
            "company": {"display_name": "Acme Ltd"},
            "location": {"display_name": "London, Greater London"},
            "salary_min": 45000, "salary_max": 65000,
            "redirect_url": "https://example.com/adzuna/a1b2c3",
        },
    ],
}

FULL_PAGE = {"results": [
    {
        "id": f"full{i}", "title": "AI Engineer",
        "description": "We need an LLM engineer with RAG experience and "
                       f"strong Python skills. Position {i}. " * 5,
        "company": {"display_name": "Acme Ltd"},
        "location": {"display_name": "London, Greater London"},
        "salary_min": 45000, "salary_max": 65000,
        "redirect_url": f"https://example.com/adzuna/full{i}",
    }
    for i in range(50)
]}


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(adzuna, "_sleep", lambda _s: None)


def _client(handler):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return AdzunaClient(app_id="id", app_key="key", http=http,
                        base_url="https://adzuna.test/v1/api/jobs")


def test_fetch_page_maps_to_raw_records():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return httpx.Response(200, json=PAGE)

    client = _client(handler)
    records = client.fetch_page(country="gb", query="LLM", page=1)
    assert len(records) == 1
    rec = records[0]
    assert rec.title == "AI Engineer"
    assert rec.company_name == "Acme Ltd"
    assert rec.city == "London, Greater London"
    assert rec.source.source_type == "public_api"
    assert rec.source.source_name == "adzuna"
    assert rec.source.source_url == "https://example.com/adzuna/a1b2c3"
    assert rec.salary_max == 65000
    assert "app_id=id" in str(calls[0])


def test_retry_on_500_then_success():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(500)
        return httpx.Response(200, json=PAGE)

    client = _client(handler)
    records = client.fetch_page("gb", "LLM", 1)
    assert attempts["n"] == 2 and len(records) == 1


def test_upstream_error_after_3_retries():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = _client(handler)
    with pytest.raises(RuntimeError, match="Adzuna"):
        client.fetch_page("gb", "LLM", 1)


def test_quota_guard_blocks_over_limit(clean_db):
    with clean_db.cursor() as cur:
        for _ in range(250):
            cur.execute(
                "INSERT INTO ingest_request_log (source_name) VALUES ('adzuna')")
    clean_db.commit()
    with pytest.raises(RuntimeError, match="额度"):
        check_daily_quota(clean_db, limit=250)


def test_fetch_adzuna_pipeline_integration(clean_db):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=PAGE)

    client = _client(handler)
    report = fetch_adzuna(clean_db, country="gb", query="LLM",
                          max_results=10, client=client)
    assert report.total >= 1
    assert report.inserted >= 1
    assert report.attribution == ADZUNA_ATTRIBUTION
    with clean_db.cursor() as cur:
        cur.execute("SELECT market, language, source_type FROM job")
        row = cur.fetchone()
        cur.execute("SELECT count(*) AS c FROM ingest_checkpoint "
                    "WHERE source_name='adzuna'")
        ckpt = cur.fetchone()["c"]
    assert row["market"] == "global"           # 无污染（验收红线）
    assert row["source_type"] == "public_api"
    assert ckpt == 1                            # checkpoint 已记录


def test_request_log_records_real_status_codes():
    """额度日志记录每次 HTTP 尝试的真实状态码（含重试，不恒为 200）。"""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(500)
        return httpx.Response(200, json=PAGE)

    logged: list[int] = []
    client = _client(handler)
    client.fetch_page("gb", "LLM", 1, log_request=logged.append)
    assert logged == [500, 200]


def test_fetch_adzuna_mid_batch_failure_keeps_partial(clean_db):
    """第 2 页重试耗尽失败：第 1 页 50 条照常入库，checkpoint 停在第 1 页。"""
    def handler(request: httpx.Request) -> httpx.Response:
        if "/search/2" in str(request.url):
            return httpx.Response(503)
        return httpx.Response(200, json=FULL_PAGE)

    client = _client(handler)
    report = fetch_adzuna(clean_db, country="gb", query="LLM",
                          max_results=100, client=client)
    assert report.inserted == 50
    assert report.total == 50
    with clean_db.cursor() as cur:
        cur.execute("SELECT last_page FROM ingest_checkpoint "
                    "WHERE source_name='adzuna'")
        assert cur.fetchone()["last_page"] == 1


def test_fetch_adzuna_resumes_from_checkpoint(clean_db):
    """续拉：第二次运行从 last_page+1 开始，不再重拉第 1 页。"""
    seen_pages: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_pages.append(str(request.url))
        return httpx.Response(200, json=PAGE)

    client = _client(handler)
    fetch_adzuna(clean_db, "gb", "LLM", max_results=10, client=client)
    fetch_adzuna(clean_db, "gb", "LLM", max_results=10, client=client)
    with clean_db.cursor() as cur:
        cur.execute("SELECT last_page FROM ingest_checkpoint "
                    "WHERE source_name='adzuna'")
        assert cur.fetchone()["last_page"] == 2
    assert any("/search/1" in u for u in seen_pages[:1])
    assert "/search/2" in seen_pages[-1]
    assert sum(1 for u in seen_pages if "/search/1" in u) == 1  # 未重拉第 1 页
