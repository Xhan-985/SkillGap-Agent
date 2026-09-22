"""质量端点（API.md §2.13 quality/report + §2.15 eval/results——纯 SQL 零 LLM）。

D3 纪律：service 超集输出 → 契约形状裁剪（batches_today/job_count/
pii_hit_total 等超集字段不外露）；eval 差异摘要复用报告口径（同版本
三元组优先，跨版本明示——§9 诚实优先）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from skillgap.api.deps import get_conn
from skillgap.eval.report import runs_payload
from skillgap.quality_metrics import quality_report

router = APIRouter(prefix="/api", tags=["quality"])


@router.get("/quality/report")
def get_quality_report(conn=Depends(get_conn)):
    """§2.13 数据质量五指标：批次三率（ingest_batch 聚合）+ 全库扫描
    两率 + PII 检测（manual_audit_pass 人工抽查后回填，如实为 null）。"""
    out = quality_report(conn)
    pii = out["pii_detection"]
    return {
        "duplicate_rate": out["duplicate_rate"],
        "missing_field_rate": out["missing_field_rate"],
        "pii_detection": {
            "rules_version": pii["rules_version"],
            "scan_count": pii["scan_count"],
            "hit_rate": pii["hit_rate"],
            "manual_audit_pass": pii["manual_audit_pass"],
        },
        "invalid_jd_rate": out["invalid_jd_rate"],
        "skill_extraction_error_rate": out["skill_extraction_error_rate"],
        "computed_at": out["computed_at"],
    }


@router.get("/eval/results")
def get_eval_results(conn=Depends(get_conn)):
    """§2.15 评测历史列表（指标 + 版本三元组 + 差异摘要）。"""
    return {"runs": runs_payload(conn)}
