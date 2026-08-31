"""S4/S5：PII 检测与脱敏（确定性正则规则库，版本化）。

诚实边界（DATA_GOVERNANCE §4）：不声称 100% 覆盖；
三层防线 = 规则（本模块）→ 人工抽查 → quarantine 复核。
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

PII_RULES_VERSION = "v1"


@dataclass(frozen=True)
class PIIFinding:
    pii_type: str
    start: int
    end: int
    matched: str
    rule_id: str


class RedactionError(Exception):
    """脱敏失败（fail-closed：整条拒绝进入市场数据集）。"""


REDACTION_MARKERS = {
    "phone": "[PHONE_REDACTED]",
    "email": "[EMAIL_REDACTED]",
    "wechat": "[WECHAT_REDACTED]",
    "qq": "[QQ_REDACTED]",
    "contact": "[CONTACT_REDACTED]",
    "id_card": "[ID_REDACTED]",
}

# 规则顺序影响重叠去留：先具体（长模式）后宽泛
# 手机号 11 位 = 1[3-9] + 9 位数字；分隔符只允许出现在数字之间
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?86[\s-]?)?1[3-9]\d(?:[\s-]?\d){8}(?!\d)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_WECHAT_RE = re.compile(
    r"(?:微信|wechat|WeChat|V信|vx|VX)\s*[:：]?\s*[A-Za-z][A-Za-z0-9_-]{5,19}")
_QQ_RE = re.compile(r"(?:扣扣|QQ|qq|Q群|q群)\s*[:：]?\s*(?<!\d)[1-9]\d{4,10}(?!\d)")
_CONTACT_RE = re.compile(
    r"(?:联系人|招聘负责人|简历接收人|HR|hr)\s*[:：]?\s*[\u4e00-\u9fa5]{2,4}")
_ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")

_ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
_ID_CHECK_MAP = "10X98765432"


def _valid_id_card_checksum(s: str) -> bool:
    total = sum(int(s[i]) * _ID_WEIGHTS[i] for i in range(17))
    return _ID_CHECK_MAP[total % 11] == s[17].upper()


def detect_pii(text: str) -> list[PIIFinding]:
    """规则检测（S4）。返回按位置排序、互不重叠的命中列表。"""
    raw: list[PIIFinding] = []

    def add(pii_type: str, m: re.Match) -> None:
        raw.append(PIIFinding(pii_type, m.start(), m.end(), m.group(0),
                              f"{PII_RULES_VERSION}:{pii_type}"))

    for m in _ID_CARD_RE.finditer(text):
        if _valid_id_card_checksum(m.group(0)):
            add("id_card", m)
    for m in _PHONE_RE.finditer(text):
        add("phone", m)
    for m in _EMAIL_RE.finditer(text):
        add("email", m)
    for m in _WECHAT_RE.finditer(text):
        add("wechat", m)
    for m in _QQ_RE.finditer(text):
        add("qq", m)
    for m in _CONTACT_RE.finditer(text):
        add("contact", m)

    # 去重叠：保留先出现（更长/更具体的规则已在顺序上优先）
    findings: list[PIIFinding] = []
    covered_until = -1
    for f in sorted(raw, key=lambda x: (x.start, -(x.end - x.start))):
        if f.start >= covered_until:
            findings.append(f)
            covered_until = f.end
    return findings


def redact(text: str, findings: list[PIIFinding]) -> tuple[str, dict]:
    """替换为类型标记（S5）。位置非法即抛 RedactionError（fail-closed）。"""
    out: list[str] = []
    pos = 0
    for f in sorted(findings, key=lambda x: x.start):
        if f.start < pos or f.start >= f.end or f.end > len(text):
            raise RedactionError(f"非法 PII 跨度: {f}")
        out.append(text[pos:f.start])
        out.append(REDACTION_MARKERS[f.pii_type])
        pos = f.end
    out.append(text[pos:])
    hits = Counter(f.pii_type for f in findings)
    report = {"rules_version": PII_RULES_VERSION, "hits": dict(hits)}
    return "".join(out), report
