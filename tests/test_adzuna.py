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
