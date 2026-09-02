"""S7 质检：pass / quarantine / reject（G4 有效性门禁）。"""
from __future__ import annotations

from dataclasses import dataclass, field

from skillgap.ingest.normalize import detect_language

MIN_LEN, MAX_LEN = 50, 20000

_JOB_SIGNAL = ["工程师", "开发", "研发", "技术", "算法", "实习", "经理", "架构师",
               "专员", "分析师", "评测", "scientist", "engineer", "developer",
               "manager", "ai", "人工智能", "大模型", "llm", "agent", "智能体",
               "rag", "后端", "前端", "全栈", "软件", "数据"]

_SPAM_MARKERS = ["刷单", "兼职日结", "点击链接", "稳赚", "日入", "带赚", "零门槛高薪"]


@dataclass
class QualityVerdict:
    verdict: str                     # pass / quarantine / reject
    language: str | None = None
    reasons: list[str] = field(default_factory=list)


def validate_jd(title: str, text: str) -> QualityVerdict:
    reasons: list[str] = []
    stripped = text.strip()

    if not (MIN_LEN <= len(stripped) <= MAX_LEN):
        reasons.append("length")
    language = detect_language(stripped)
    if language is None:
        reasons.append("language_unidentifiable")

    if not title or not title.strip():
        reasons.append("empty_title")
    else:
        title_fold = title.casefold()
        if not any(sig.casefold() in title_fold for sig in _JOB_SIGNAL):
            reasons.append("title_no_job_signal")

    if any(marker in stripped for marker in _SPAM_MARKERS):
        return QualityVerdict("reject", language, reasons + ["spam"])

    # 模板文本：行数足够且重复率极高
    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    if len(lines) >= 8 and len(set(lines)) / len(lines) < 0.5:
        reasons.append("template_like")

    if reasons:
        return QualityVerdict("quarantine", language, reasons)
    return QualityVerdict("pass", language, reasons)
