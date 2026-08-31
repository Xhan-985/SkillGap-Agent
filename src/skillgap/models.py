"""管道内部数据契约（防腐层 Schema——DATA_PIPELINE S1 输出 RawRecord）。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SourceTypeEnum = Literal[
    "public_api", "public_job_page", "user_submitted", "csv_import", "dataset_builtin"
]
MarketEnum = Literal["china", "global"]
LanguageEnum = Literal["zh", "en"]
ConsentEnum = Literal["none", "market_analysis"]
DataQualityEnum = Literal["verified", "auto_passed", "human_reviewed", "suspect"]
ImportanceEnum = Literal["must_have", "nice_to_have"]
IntensityEnum = Literal["精通", "熟练", "熟悉", "了解"]


class SourceFields(BaseModel):
    """来源九字段（DATA_GOVERNANCE §2）——每条 Job 强制。"""
    source_type: SourceTypeEnum
    source_name: str
    source_url: str | None = None
    collected_at: datetime
    submitted_at: datetime | None = None
    content_hash: str = ""          # 由管道 S6 计算
    license_or_usage_note: str = ""
    consent_status: ConsentEnum = "none"
    data_quality: DataQualityEnum = "auto_passed"


class SkillAnnotation(BaseModel):
    """S8 抽取输出的技能项（LLM 或人工标注共用同一 Schema）。"""
    raw_name: str
    importance: ImportanceEnum
    intensity: IntensityEnum | None = None
    evidence_text: str


class RawRecord(BaseModel):
    title: str
    raw_text: str
    company_name: str | None = None
    city: str | None = None
    country: str | None = None
    region: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    job_category: str | None = None    # 空 = S3 规则归类
    soft_requirements: list[dict] | None = None
    suggested_skills: list[SkillAnnotation] = Field(default_factory=list)
    source: SourceFields


SoftReqTypeEnum = Literal["experience", "education", "language"]


class SoftRequirement(BaseModel):
    type: SoftReqTypeEnum
    value: str
    evidence_text: str


class JDExtraction(BaseModel):
    """LLM 抽取输出契约（ADR-009）。证据可溯由 extract 层程序校验。"""
    skills: list[SkillAnnotation]
    soft_requirements: list[SoftRequirement] = Field(default_factory=list)


class RowError(BaseModel):
    row: int
    stage: str
    message: str


class BatchReport(BaseModel):
    """导入/ingest/贡献批次报告（API §2.3 契约对齐）。"""
    source_name: str
    total: int = 0
    inserted: int = 0
    duplicates: int = 0
    quarantined: int = 0
    rejected: int = 0
    extraction_failed: int = 0
    errors: list[RowError] = Field(default_factory=list)
    attribution: str | None = None
