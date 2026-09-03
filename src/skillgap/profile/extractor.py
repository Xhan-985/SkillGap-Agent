"""LLMResumeExtractor（Phase 5）——复用 Phase 3 抽取器模式。

失败语义对齐 ADR-009：Schema 违反或证据不可溯 → 携带校验错误重试 ≤2 →
仍失败抛 ExtractionFailed（上层明示，不降级不静默）。
"""
from __future__ import annotations

import json

from skillgap.extract.llm_extractor import ExtractionFailed, parse_json_content
from skillgap.ingest.extract import locate_evidence
from skillgap.llm.gateway import LLMGateway
from skillgap.models import ResumeExtraction
from skillgap.profile.prompt import resume_messages


class LLMResumeExtractor:
    def __init__(self, gateway: LLMGateway, max_retries: int = 2):
        self.gateway = gateway
        self.max_retries = max_retries
        self.last_usage: dict = {}

    def extract_full(self, resume_text: str) -> ResumeExtraction:
        last_error: Exception | None = None
        messages = resume_messages(resume_text)
        for _attempt in range(self.max_retries + 1):
            resp = self.gateway.chat(messages, response_json=True)
            self.last_usage = {"total_tokens": resp.total_tokens,
                               "model": resp.model}
            try:
                data = parse_json_content(resp.content)
                result = ResumeExtraction.model_validate(data)
                self._validate_evidence(resume_text, result)
                return result
            except (json.JSONDecodeError, ValueError) as e:
                last_error = e
                messages = messages[:2] + [
                    {"role": "assistant", "content": resp.content},
                    {"role": "user", "content":
                     f"输出未通过校验：{e}。请严格按规则重新输出 JSON"
                     "（evidences[].text 必须是简历原文同一段连续片段，"
                     "skills 每项必含 raw_name/level 1-5/evidences）。"},
                ]
        raise ExtractionFailed(
            f"简历抽取重试 {self.max_retries} 次后仍失败: {last_error}")

    @staticmethod
    def _validate_evidence(resume_text: str,
                           result: ResumeExtraction) -> None:
        for s in result.skills:
            for ev in s.evidences:
                if not locate_evidence(resume_text, ev.text):
                    raise ValueError(
                        f"证据无法在简历原文定位: {ev.text!r}")
        for field in ("experience_years", "education", "languages"):
            soft = getattr(result.soft_profile, field)
            if soft is not None and not locate_evidence(
                    resume_text, soft.evidence_text):
                raise ValueError(f"soft_profile.{field} 证据无法定位: "
                                 f"{soft.evidence_text!r}")
