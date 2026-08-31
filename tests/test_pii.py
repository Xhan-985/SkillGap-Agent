import pytest

from skillgap.ingest.pii import (
    PIIFinding, RedactionError, detect_pii, redact, PII_RULES_VERSION,
)


def test_detect_phone_basic_and_variants():
    text = "联系电话 13812345678，或 +86 15987654321 / 186-0000-1111"
    findings = detect_pii(text)
    phones = [f for f in findings if f.pii_type == "phone"]
    assert len(phones) == 3
    assert all(f.rule_id.startswith("v1:") for f in phones)


def test_detect_phone_not_matched_inside_long_digits():
    # 20 位连续数字不是手机号
    assert detect_pii("订单号 13812345678123456789") == [] or \
        all(f.pii_type != "phone" for f in detect_pii("订单号 13812345678123456789"))


def test_detect_email():
    findings = detect_pii("简历投递 hr@example.com 谢谢")
    assert any(f.pii_type == "email" for f in findings)


def test_detect_wechat_and_qq():
    text = "加微信 w_xiaoming123 或 QQ： 123456789"
    findings = detect_pii(text)
    assert any(f.pii_type == "wechat" for f in findings)
    assert any(f.pii_type == "qq" for f in findings)


def test_detect_id_card_with_valid_checksum():
    # 有效的 18 位身份证（校验位通过）
    text = "身份证号 11010519491231002X 请登记"
    findings = detect_pii(text)
    assert any(f.pii_type == "id_card" for f in findings)


def test_detect_id_card_invalid_checksum_not_flagged():
    # 18 位但校验位错误 → 不标记（降低误报）
    text = "编号 110105194912310021 请登记"
    assert all(f.pii_type != "id_card" for f in detect_pii(text))


def test_detect_contact_name():
    findings = detect_pii("联系人：王大力，联系电话见上")
    assert any(f.pii_type == "contact" for f in findings)


def test_redact_replaces_all_types():
    text = "联系张三 13812345678，邮箱 a@b.com，微信 abc_12345，QQ 12345678"
    redacted, report = redact(text, detect_pii(text))
    assert "[PHONE_REDACTED]" in redacted
    assert "[EMAIL_REDACTED]" in redacted
    assert "[WECHAT_REDACTED]" in redacted
    assert "[QQ_REDACTED]" in redacted
    assert report["rules_version"] == PII_RULES_VERSION
    assert report["hits"]["phone"] == 1


def test_redact_keeps_readability_and_text_length_reasonable():
    text = "负责 RAG 系统开发。手机 13812345678。要求熟悉 LangChain。"
    redacted, _ = redact(text, detect_pii(text))
    assert "RAG" in redacted and "LangChain" in redacted
    assert "13812345678" not in redacted


def test_redact_fail_closed_on_bad_span():
    bad = [PIIFinding(pii_type="phone", start=5, end=2,
                      matched="x", rule_id="v1:phone")]
    with pytest.raises(RedactionError):
        redact("normal text", bad)


def test_clean_text_yields_no_findings():
    text = "岗位要求：熟悉大模型应用开发，掌握 RAG 与 Agent 编排，3 年以上经验。"
    assert detect_pii(text) == []
