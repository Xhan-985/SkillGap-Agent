"""S1 CSV/JSON 批量导入器（Tier C；列规格 = DATA_MODEL §7）。

CSV 表头支持中文（collect_template.csv 现用）或英文（旧格式），
导入时统一映射为内部字段名后再校验/解析。
"""
from __future__ import annotations

import csv
import json
import warnings
from pathlib import Path

from skillgap.models import RawRecord, SkillAnnotation, SourceFields

REQUIRED_COLUMNS = {
    "title", "raw_text", "source_type", "source_name", "collected_at",
}

# 中文表头 → 内部字段名（值/枚举仍为英文；仅表头可中文）
HEADER_ALIASES = {
    "岗位名称": "title",
    "标题": "title",
    "公司": "company",
    "城市": "city",
    "国家": "country",
    "区域": "region",
    "最低薪资": "salary_min",
    "最高薪资": "salary_max",
    "薪资货币": "salary_currency",
    "岗位类别": "job_category",
    "JD全文": "raw_text",
    "软性要求": "soft_requirements",
    "技能标注": "skills",
    "来源类型": "source_type",
    "来源名称": "source_name",
    "来源链接": "source_url",
    "采集日期": "collected_at",
    "提交时间": "submitted_at",
    "同意状态": "consent_status",
    "数据质量": "data_quality",
}


def _map_headers(rows: list[dict]) -> list[dict]:
    """把中文表头键映射为内部字段名（未知键原样保留，None 键丢弃）。"""
    return [{HEADER_ALIASES.get(k, k): v for k, v in r.items()
             if k is not None} for r in rows]


def parse_file(path: str | Path) -> list[RawRecord]:
    p = Path(path)
    if p.suffix.lower() == ".csv":
        with p.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        rows = _map_headers(rows)
        if rows and not REQUIRED_COLUMNS.issubset(rows[0].keys()):
            missing = REQUIRED_COLUMNS - set(rows[0].keys())
            raise ValueError(f"CSV 缺少必需列: {sorted(missing)}（整批拒绝）")
        return _from_rows(rows, p, start=2)  # 表头占第 1 行
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("JSON 顶层必须是数组（整批拒绝）")
        return _from_rows(data, p, start=1)
    raise ValueError(f"不支持的文件类型: {p.suffix}（仅 CSV/JSON）")


def _from_rows(rows: list, path: Path, start: int) -> list[RawRecord]:
    records: list[RawRecord] = []
    for i, row in enumerate(rows, start=start):
        try:
            records.append(_to_record(row))
        except Exception as e:
            warnings.warn(f"{path.name} 第 {i} 行解析失败，已跳过: {e}", UserWarning)
    return records


def _to_record(row: dict) -> RawRecord:
    skills_raw = row.get("skills") or "[]"
    if isinstance(skills_raw, str):
        skills_raw = json.loads(skills_raw)
    source = SourceFields(
        source_type=row["source_type"],
        source_name=row["source_name"],
        source_url=row.get("source_url") or None,
        collected_at=row["collected_at"],
        submitted_at=row.get("submitted_at") or None,
        license_or_usage_note=row.get("license_or_usage_note", ""),
        consent_status=row.get("consent_status") or "none",
        data_quality=row.get("data_quality") or "auto_passed",
    )
    soft = row.get("soft_requirements") or None
    if isinstance(soft, str):
        soft = json.loads(soft)
    job_category = (row.get("job_category") or "").strip() or None
    return RawRecord(
        title=row["title"],
        raw_text=row["raw_text"],
        company_name=row.get("company") or None,
        city=row.get("city") or None,
        country=row.get("country") or None,
        region=row.get("region") or None,
        salary_min=_int_or_none(row.get("salary_min")),
        salary_max=_int_or_none(row.get("salary_max")),
        salary_currency=row.get("salary_currency") or None,
        job_category=job_category,
        soft_requirements=soft,
        suggested_skills=[SkillAnnotation(**s) for s in skills_raw],
        source=source,
    )


def _int_or_none(v):
    if v in (None, ""):
        return None
    return int(float(v))
