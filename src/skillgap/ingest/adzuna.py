"""S1 Adzuna 连接器（Tier A，Global 专用）。

合规（DATA_GOVERNANCE §6）：
- 仓库只分发连接器代码，不分发数据（用户自行运行 ingest）；
- 遵守免费层限额（本地额度守卫前置）；
- 展示层带 "Jobs by Adzuna" 归属。
失败处理（DATA_PIPELINE S1）：429/5xx 指数退避重试 ≤3，仍失败记录 checkpoint 次日续拉。
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx
import psycopg

from skillgap.ingest.pipeline import run_batch
from skillgap.models import BatchReport, RawRecord, SourceFields

ADZUNA_ATTRIBUTION = "Jobs by Adzuna"
RESULTS_PER_PAGE = 50
MAX_RETRIES = 3

_sleep = time.sleep  # 测试可注入（monkeypatch skillgap.ingest.adzuna._sleep）


class AdzunaClient:
    def __init__(self, app_id: str, app_key: str,
                 http: httpx.Client | None = None,
                 base_url: str = "https://api.adzuna.com/v1/api/jobs"):
        self.app_id = app_id
        self.app_key = app_key
        self.base_url = base_url.rstrip("/")
        self.http = http or httpx.Client(timeout=10.0)

    def fetch_page(self, country: str, query: str, page: int,
                   log_request=None) -> list[RawRecord]:
        params = {
            "app_id": self.app_id, "app_key": self.app_key,
            "results_per_page": RESULTS_PER_PAGE, "what": query, "page": page,
        }
        url = f"{self.base_url}/{country}/search/{page}"
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = self.http.get(url, params=params)
                if log_request:
                    # 每次 HTTP 尝试记录真实状态码（额度守卫按此计数，含重试）
                    log_request(resp.status_code)
                if resp.status_code in (429, 500, 502, 503, 504):
                    retry_after = resp.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 2 ** attempt
                    _sleep(min(delay, 30))
                    last_error = RuntimeError(
                        f"Adzuna 返回 {resp.status_code}")
                    continue
                resp.raise_for_status()
                return self._map_results(resp.json(), country)
            except (httpx.HTTPError, RuntimeError) as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    _sleep(2 ** attempt)
        raise RuntimeError(f"Adzuna 重试 {MAX_RETRIES} 次后仍失败: {last_error}")

    def _map_results(self, payload: dict, country: str) -> list[RawRecord]:
        now = datetime.now(timezone.utc)
        records = []
        for item in payload.get("results", []):
            company = (item.get("company") or {}).get("display_name")
            location = (item.get("location") or {}).get("display_name")
            records.append(RawRecord(
                title=item.get("title") or "",
                raw_text=item.get("description") or "",
                company_name=company,
                city=location,
                country=country.upper(),
                salary_min=item.get("salary_min"),
                salary_max=item.get("salary_max"),
                salary_currency=None,
                source=SourceFields(
                    source_type="public_api",
                    source_name="adzuna",
                    source_url=item.get("redirect_url"),
                    collected_at=now,
                    license_or_usage_note="Adzuna ToS: attribution + no redistribution",
                ),
            ))
        return records


def check_daily_quota(conn: psycopg.Connection, limit: int = 250) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS c FROM ingest_request_log "
            "WHERE source_name='adzuna' AND requested_at::date = CURRENT_DATE")
        used = cur.fetchone()["c"]
    if used >= limit:
        raise RuntimeError(
            f"本地额度守卫：Adzuna 今日已用 {used}/{limit} 请求（DATA_GOVERNANCE §6）")


def _log_request(conn, status_code: int | None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ingest_request_log (source_name, status_code) "
            "VALUES ('adzuna', %s)", (status_code,))
    conn.commit()


def _save_checkpoint(conn, country: str, query: str, page: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO ingest_checkpoint (source_name, scope_key, last_page)
               VALUES ('adzuna', %s, %s)
               ON CONFLICT (source_name, scope_key)
               DO UPDATE SET last_page = EXCLUDED.last_page, updated_at = now()""",
            (f"country:{country}|query:{query}", page))
    conn.commit()


def _load_checkpoint(conn, country: str, query: str) -> int:
    """续拉：返回上次成功拉取的页号（0 = 无 checkpoint）。"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_page FROM ingest_checkpoint "
            "WHERE source_name='adzuna' AND scope_key=%s",
            (f"country:{country}|query:{query}",))
        row = cur.fetchone()
    return row["last_page"] if row else 0


def fetch_adzuna(conn: psycopg.Connection, country: str, query: str,
                 max_results: int = 500,
                 client: AdzunaClient | None = None) -> BatchReport:
    """拉取 → S3-S10 管道入库。market=global 由 data_source + 服务层双保险。

    失败语义（S1）：某页重试耗尽仍失败时，已拉取页照常入库（不丢弃），
    checkpoint 停在最后成功页，次日续拉从 last_page+1 开始。
    """
    from skillgap.config import settings

    check_daily_quota(conn, limit=settings.adzuna_daily_quota)
    client = client or AdzunaClient(settings.adzuna_app_id,
                                    settings.adzuna_app_key,
                                    base_url=settings.adzuna_base_url)
    pages = (max_results + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
    start = _load_checkpoint(conn, country, query) + 1
    all_records: list[RawRecord] = []
    for page in range(start, start + pages):
        try:
            records = client.fetch_page(
                country, query, page,
                log_request=lambda code: _log_request(conn, code))
        except RuntimeError:
            if not all_records:
                raise  # 首页即失败：无数据可入库，向上报错
            break   # 已拉记录照常入库；checkpoint 次日续拉
        all_records.extend(records)
        _save_checkpoint(conn, country, query, page)
        if len(records) < RESULTS_PER_PAGE:
            break
    report = run_batch(conn, all_records)
    report.attribution = ADZUNA_ATTRIBUTION
    return report
