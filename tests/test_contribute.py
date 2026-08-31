import pytest

from skillgap.ingest.contribute import (
    ContributeResult, contribute_jd, delete_contribution,
)

JD = ("岗位职责：负责大模型应用开发，搭建 RAG 检索链路与 Agent 编排。"
      "任职要求：熟悉 LangChain，精通 Python。") * 2


def test_contribute_requires_consent(clean_db):
    with pytest.raises(ValueError, match="consent"):
        contribute_jd(clean_db, jd_text=JD, consent=False, title="AI 工程师")


def test_contribute_success_with_redaction_and_deletion_code(clean_db):
    text = "联系张三 13812345678。" + JD
    result = contribute_jd(clean_db, jd_text=text, consent=True,
                           title="AI 应用开发工程师", source_hint="boss")
    assert result.deduplicated is False
    assert result.job_id > 0
    assert len(result.deletion_code) >= 8
    assert result.pii_redaction["hits"]["phone"] == 1
    with clean_db.cursor() as cur:
        cur.execute("SELECT raw_text, consent_status, market, source_type,"
                    " submitted_at, status, parsed_metadata FROM job WHERE id=%s",
                    (result.job_id,))
        row = cur.fetchone()
    assert "13812345678" not in row["raw_text"]
    assert row["consent_status"] == "market_analysis"
    assert row["source_type"] == "user_submitted"
    assert row["market"] == "china"
    assert row["submitted_at"] is not None
    assert row["status"] == "active"
    assert row["parsed_metadata"]["source_hint"] == "boss"


def test_duplicate_contribution_returns_existing(clean_db):
    a = contribute_jd(clean_db, JD, True, "AI 工程师")
    b = contribute_jd(clean_db, JD, True, "AI 工程师")
    assert b.deduplicated is True
    assert b.job_id == a.job_id
    assert b.deletion_code is None      # 重复提交不发新 code


def test_delete_by_code_roundtrip(clean_db):
    r = contribute_jd(clean_db, JD, True, "AI 工程师")
    assert delete_contribution(clean_db, r.deletion_code) is True
    with clean_db.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM job WHERE id=%s", (r.job_id,))
        assert cur.fetchone()["c"] == 0
    # 错误 code 返回 False（不区分不存在/已删——防探测，API §2.14）
    assert delete_contribution(clean_db, r.deletion_code) is False


def test_quarantined_contribution_raises(clean_db):
    with pytest.raises(RuntimeError, match="quarantine"):
        contribute_jd(clean_db, jd_text="太短的JD", consent=True, title="x工程师")
