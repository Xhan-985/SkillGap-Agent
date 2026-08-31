"""LLM SkillExtractor（实现 Phase 2 冻结的 SkillExtractor 协议）。

失败语义（ADR-009 / API.md §2.1）：Schema 违反或证据不可溯 → 携带校验错误
重试 ≤2 → 仍失败抛 ExtractionFailed（上层明示 LLM_EXTRACTION_FAILED，不降级不静默）。
"""
from __future__ import annotations

import json

from skillgap.extract.prompt import extraction_messages
from skillgap.ingest.extract import locate_evidence
from skillgap.llm.gateway import LLMGateway
from skillgap.models import JDExtraction, SkillAnnotation


class ExtractionFailed(RuntimeError):
    """抽取失败（Schema/证据校验，重试后）——明示，不降级。"""


def _parse_content(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text[:4].lower() == "json":
            text = text[4:].strip()
    return json.loads(text)


class LLMSkillExtractor:
    def __init__(self, gateway: LLMGateway, max_retries: int = 2):
        self.gateway = gateway
        self.max_retries = max_retries
        self.last_usage: dict = {}

    def extract(self, jd_text: str) -> list[SkillAnnotation]:
        """SkillExtractor 协议适配（Phase 2 冻结接口）。"""
        return self.extract_full(jd_text).skills

    def extract_full(self, jd_text: str) -> JDExtraction:
        """主流程：完整抽取（skills + soft_requirements）。"""
        last_error: Exception | None = None
        messages = extraction_messages(jd_text)
        for _attempt in range(self.max_retries + 1):
            resp = self.gateway.chat(messages, response_json=True)
            self.last_usage = {"total_tokens": resp.total_tokens,
                               "model": resp.model}
            try:
                data = _parse_content(resp.content)
                result = JDExtraction.model_validate(data)
                self._validate_evidence(jd_text, result)
                return result
            except (json.JSONDecodeError, ValueError) as e:
                last_error = e
                # 对话式纠错：反馈校验错误，保留原 JD 上下文
                messages = messages[:2] + [
                    {"role": "assistant", "content": resp.content},
                    {"role": "user", "content":
                     f"输出未通过校验：{e}。请严格按规则重新输出 JSON"
                     "（evidence_text 必须是 JD 原文连续片段，"
                     "skills 每项必含 raw_name/importance/evidence_text）。"},
                ]
        raise ExtractionFailed(
            f"抽取重试 {self.max_retries} 次后仍失败: {last_error}")

    @staticmethod
    def _validate_evidence(jd_text: str, result: JDExtraction) -> None:
        for s in result.skills:
            if not locate_evidence(jd_text, s.evidence_text):
                raise ValueError(
                    f"evidence_text 无法在 JD 原文定位: {s.evidence_text!r}")
        for r in result.soft_requirements:
            if not locate_evidence(jd_text, r.evidence_text):
                raise ValueError(
                    f"soft_requirement 证据无法定位: {r.evidence_text!r}")
