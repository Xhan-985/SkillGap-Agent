"""S3 规范化 + S6 哈希去重（全部确定性规则，无 LLM）。"""
from __future__ import annotations

import hashlib
import re
import unicodedata

_WS_RE = re.compile(r"\s+")
_CJK_RE = re.compile(r"[\u4e00-\u9fa5]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def canonicalize_for_hash(text: str) -> str:
    """去重规范化：NFKC（全角→半角）→ casefold → 折叠空白。"""
    text = unicodedata.normalize("NFKC", text).casefold()
    return _WS_RE.sub(" ", text).strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(canonicalize_for_hash(text).encode("utf-8")).hexdigest()


def detect_language(text: str) -> str | None:
    cjk = len(_CJK_RE.findall(text))
    latin = len(_LATIN_RE.findall(text))
    total = cjk + latin
    if total == 0:
        return None
    return "zh" if cjk / total >= 0.3 else "en"


def determine_market(language: str | None, covers_market: str) -> str | None:
    """市场判定：来源覆盖权威；both 时按主体语言；无法判定返回 None（上层标 ambiguous）。"""
    if covers_market in ("china", "global"):
        return covers_market
    if language == "zh":
        return "china"
    if language == "en":
        return "global"
    return None


_SALARY_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(万|[kK])?\s*[-~至到～]\s*(\d+(?:\.\d+)?)\s*(万|[kK])?")


def parse_salary_range(text: str) -> tuple[int | None, int | None]:
    m = _SALARY_RE.search(text)
    if not m:
        return None, None
    lo, hi = float(m.group(1)), float(m.group(3))
    unit = m.group(2) or m.group(4)
    if unit == "万":
        lo, hi = lo * 10000, hi * 10000
    elif unit in ("k", "K"):
        lo, hi = lo * 1000, hi * 1000
    else:  # 无单位：小数值按 K 处理
        if lo < 200 and hi < 200:
            lo, hi = lo * 1000, hi * 1000
    return int(lo), int(hi)


_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "ai_application_dev": ["ai应用", "大模型应用", "llm应用", "ai工程师", "算法应用",
                           "ai产品", "aigc", "生成式"],
    "agent_dev": ["agent", "智能体", "multi-agent"],
    "llm_fullstack": ["全栈", "full stack", "fullstack"],
    "mcp_dev": ["mcp", "model context protocol"],
    "ai_platform": ["机器学习平台", "ml平台", "ai平台", "ai infra", "mlops",
                    "machine learning platform", "推理服务", "模型部署", "平台工程"],
    "python_ai_dev": ["python开发", "python工程师", "python后端", "django", "flask",
                      "fastapi"],
    "dify_dev": ["dify", "coze", "扣子", "工作流编排"],
}


def classify_job_category(title: str, text: str = "") -> str:
    """岗位类别词表 v1 规则归类（DATA_MODEL §5.1）。

    匹配前去除空白：标题中英/中词间空格（"AI 应用"）不应造成漏配。
    """
    hay = _WS_RE.sub("", f"{title}\n{text[:500]}").casefold()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(_WS_RE.sub("", k) in hay for k in keywords):
            return category
    return "other"
