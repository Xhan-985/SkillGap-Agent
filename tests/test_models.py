from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from skillgap.models import RawRecord, SkillAnnotation, SourceFields

NOW = datetime(2026, 8, 31, tzinfo=timezone.utc)


def test_source_fields_requires_source_type():
    with pytest.raises(ValidationError):
        SourceFields(source_name="x", collected_at=NOW)


def test_raw_record_defaults():
    rec = RawRecord(
        title="AI 工程师", raw_text="岗位描述" * 30,
        source=SourceFields(
            source_type="public_job_page", source_name="company_career_page",
            collected_at=NOW),
    )
    assert rec.source.consent_status == "none"
    assert rec.source.data_quality == "auto_passed"
    assert rec.suggested_skills == []


def test_skill_annotation_importance_enum():
    with pytest.raises(ValidationError):
        SkillAnnotation(raw_name="RAG", importance="required", evidence_text="x")


def test_raw_record_rejects_bad_market_source():
    with pytest.raises(ValidationError):
        SourceFields(source_type="crawler", source_name="x", collected_at=NOW)
