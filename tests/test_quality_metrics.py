from datetime import datetime, timezone

from skillgap.ingest.pipeline import run_batch
from skillgap.quality_metrics import batch_metrics, full_scan
from tests.test_pipeline import _rec as make_rec  # 复用构造器

NOW = datetime(2026, 8, 31, tzinfo=timezone.utc)


def test_batch_metrics_rates(clean_db):
    records = [make_rec(), make_rec()]
    bad = make_rec(); bad.raw_text = "太短"
    records.append(bad)
    report = run_batch(clean_db, records)
    m = batch_metrics(report)
    assert m["duplicate_rate"] == round(1 / 3, 4)
    assert m["invalid_jd_rate"] == round(1 / 3, 4)
    assert m["skill_extraction_error_rate"] == 0.0


def test_full_scan_missing_field_rate_zero(clean_db):
    run_batch(clean_db, [make_rec()])
    scan = full_scan(clean_db)
    assert scan["missing_field_rate"] == 0.0
    assert scan["job_count"] == 1


def test_full_scan_pii_aggregation(clean_db):
    rec = make_rec()
    rec.source.source_type = "user_submitted"
    rec.source.source_name = "user_contribution"
    rec.source.consent_status = "market_analysis"
    rec.raw_text = "联系张三 13812345678。" + rec.raw_text
    run_batch(clean_db, [rec])
    scan = full_scan(clean_db)
    assert scan["pii_scan_count"] >= 1
    assert scan["pii_hit_total"] >= 1
    assert scan["pii_rules_version"] == "v1"
