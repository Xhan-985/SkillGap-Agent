"""Phase 11 T3：质量端点——§2.13 五指标契约形状/批次聚合/PII 口径 +
§2.15 评测历史列表（版本三元组提升 + 差异摘要三态）。"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from skillgap.api.app import create_app
from skillgap.api.deps import get_conn


@pytest.fixture()
def client(clean_db):
    """client + conn：conn 供数据工厂使用（同一 test 库连接）。"""
    app = create_app()

    def _override():
        yield clean_db

    app.dependency_overrides[get_conn] = _override
    with TestClient(app) as c:
        yield c, clean_db


def _batch(conn, name, total, inserted, duplicates, quarantined, rejected,
           extraction_failed):
    conn.execute(
        """INSERT INTO ingest_batch (source_name, source_type, total,
           inserted, duplicates, quarantined, rejected, extraction_failed)
           VALUES (%s, 'csv_import', %s, %s, %s, %s, %s, %s)""",
        (name, total, inserted, duplicates, quarantined, rejected,
         extraction_failed))
    conn.commit()


def _run(conn, eval_type, dataset_version, prompt_version, model, metrics,
         sample_size=25, verdict="warn"):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO eval_run (eval_type, dataset_version,
               prompt_version, model, metrics, sample_size, verdict)
               VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s) RETURNING id""",
            (eval_type, dataset_version, prompt_version, model,
             json.dumps(metrics), sample_size, verdict))
        rid = cur.fetchone()["id"]
    conn.commit()
    return rid


# ---------- §2.13 quality/report ----------

def test_quality_report_contract_shape(client):
    """空库 → 200 契约六键（§2.13）；除零守卫五率全 0.0；service 超集
    字段（batches_today/job_count/pii_hit_total）必须被裁剪（D3）。"""
    c, _ = client
    r = c.get("/api/quality/report")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"duplicate_rate", "missing_field_rate",
                         "pii_detection", "invalid_jd_rate",
                         "skill_extraction_error_rate", "computed_at"}
    assert body["duplicate_rate"] == 0.0
    assert body["missing_field_rate"] == 0.0
    assert body["invalid_jd_rate"] == 0.0
    assert body["skill_extraction_error_rate"] == 0.0
    assert set(body["pii_detection"]) == {"rules_version", "scan_count",
                                          "hit_rate", "manual_audit_pass"}
    assert body["pii_detection"]["scan_count"] == 0
    assert body["pii_detection"]["hit_rate"] == 0.0
    assert body["pii_detection"]["manual_audit_pass"] is None  # 如实未抽查
    assert body["computed_at"]
    # 超集字段剥离
    assert "batches_today" not in body and "job_count" not in body
    assert "hit_total" not in body["pii_detection"]


def test_quality_report_batch_rates(client):
    """批次聚合三率（ingest_batch 全历史求和，口径同 batch_metrics）：
    A(10 总/2 重/2 无效/1 抽败/5 入) + B(4 总/1 重/0 无效/0 抽败/3 入) →
    duplicate 3/14、invalid 2/14、extraction_error 1/9。"""
    c, conn = client
    _batch(conn, "a", total=10, inserted=5, duplicates=2, quarantined=1,
           rejected=1, extraction_failed=1)
    _batch(conn, "b", total=4, inserted=3, duplicates=1, quarantined=0,
           rejected=0, extraction_failed=0)
    body = c.get("/api/quality/report").json()
    assert body["duplicate_rate"] == pytest.approx(3 / 14, abs=1e-4)
    assert body["invalid_jd_rate"] == pytest.approx(2 / 14, abs=1e-4)
    assert body["skill_extraction_error_rate"] == pytest.approx(1 / 9,
                                                                abs=1e-4)


def test_quality_report_pii_and_missing(client):
    """PII：scan_count=命中脱敏记录数、hit_rate=命中总数/扫描数；
    missing_field_rate：NOT NULL 约束兜底恒 0（E5 显式口径）。"""
    from tests.test_schema import _insert_job, _job_kwargs, _source

    c, conn = client
    sid = _source(clean_db := conn)
    j1 = _insert_job(clean_db, **_job_kwargs(sid, content_hash="q1"))
    _insert_job(clean_db, **_job_kwargs(sid, content_hash="q2"))
    conn.execute(
        """UPDATE job SET parsed_metadata =
           '{"pii_redaction": {"hits": {"phone": 2, "email": 1}}}'::jsonb
           WHERE id = %s""", (j1,))
    conn.commit()
    body = c.get("/api/quality/report").json()
    assert body["pii_detection"]["scan_count"] == 1
    assert body["pii_detection"]["hit_rate"] == pytest.approx(3.0)
    assert body["missing_field_rate"] == 0.0


# ---------- §2.15 eval/results ----------

def test_eval_results_empty(client):
    """无 eval_run → 200 + 空 runs（首次跑分前的正常态）。"""
    c, _ = client
    r = c.get("/api/eval/results")
    assert r.status_code == 200
    assert r.json() == {"runs": []}


def test_eval_results_contract_shape(client):
    """历史列表契约形状：每条含指标 + 版本三元组（dataset/prompt 顶层列 +
    scoring_version 自 metrics 提升——E2 有值、E1 无则 None）。"""
    c, conn = client
    _run(conn, "skill_extraction", "e1_seed_v2", "v3", "deepseek-chat",
         {"f1": 0.80, "recall": 0.85})
    _run(conn, "matching", "e2_seed_v1", "1.0.0", "deterministic",
         {"spearman": 0.8277, "scoring_version": "1.0.0"},
         sample_size=25, verdict="pass")
    r = c.get("/api/eval/results")
    assert r.status_code == 200
    runs = r.json()["runs"]
    assert len(runs) == 2
    assert set(runs[0]) == {"id", "eval_type", "dataset_version",
                            "prompt_version", "scoring_version", "model",
                            "sample_size", "verdict", "metrics", "diff",
                            "created_at"}
    e1 = next(r for r in runs if r["eval_type"] == "skill_extraction")
    assert e1["dataset_version"] == "e1_seed_v2"
    assert e1["prompt_version"] == "v3"
    assert e1["scoring_version"] is None            # E1 metrics 无此键
    assert e1["metrics"]["f1"] == 0.80
    e2 = next(r for r in runs if r["eval_type"] == "matching")
    assert e2["scoring_version"] == "1.0.0"         # 自 metrics 提升
    assert e2["verdict"] == "pass"


def test_eval_results_diff_summary(client):
    """差异摘要三态（与报告 §2 同一 _pick_prev_for 口径）：首条无基线 /
    同版本数值 delta / 跨版本明示（口径变化不能归因系统好坏）。"""
    c, conn = client
    _run(conn, "skill_extraction", "v1", "p1", "m", {"f1": 0.80})
    _run(conn, "skill_extraction", "v1", "p1", "m", {"f1": 0.85})
    _run(conn, "skill_extraction", "v2", "p1", "m", {"f1": 0.60})
    runs = c.get("/api/eval/results").json()["runs"]
    first, second, third = runs
    # 首条：无基线
    assert first["diff"] == {"baseline_run_id": None, "baseline_kind": None,
                             "deltas": {}}
    # 第二条：同版本（dataset+prompt 一致）→ 数值 delta
    assert second["diff"]["baseline_run_id"] == first["id"]
    assert second["diff"]["baseline_kind"] == "same_version"
    assert second["diff"]["deltas"] == {"f1": 0.05}
    # 第三条：无同版本 → 退紧邻上一条，跨版本明示
    assert third["diff"]["baseline_run_id"] == second["id"]
    assert third["diff"]["baseline_kind"] == "cross_version"
    assert third["diff"]["deltas"] == {"f1": -0.25}
