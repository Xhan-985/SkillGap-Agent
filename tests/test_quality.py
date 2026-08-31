from skillgap.ingest.quality import validate_jd

GOOD_TEXT = "岗位描述：" + "负责大模型应用开发与RAG链路优化。" * 10


def test_pass_normal_jd():
    v = validate_jd("AI 应用开发工程师", GOOD_TEXT)
    assert v.verdict == "pass"
    assert v.language == "zh"


def test_too_short_quarantined():
    v = validate_jd("AI 工程师", "太短")
    assert v.verdict == "quarantine"
    assert "length" in v.reasons


def test_too_long_quarantined():
    v = validate_jd("AI 工程师", "x" * 20001)
    assert v.verdict == "quarantine"
    assert "length" in v.reasons


def test_unidentifiable_language_quarantined():
    v = validate_jd("AI 工程师", "1234 5678 9012 " * 10)
    assert v.verdict == "quarantine"
    assert "language_unidentifiable" in v.reasons


def test_title_without_job_signal_quarantined():
    v = validate_jd("星辰大海", GOOD_TEXT)
    assert v.verdict == "quarantine"
    assert "title_no_job_signal" in v.reasons


def test_empty_title_quarantined():
    v = validate_jd("", GOOD_TEXT)
    assert v.verdict == "quarantine"


def test_spam_rejected():
    v = validate_jd("招聘专员", "日入五百，点击链接马上赚钱，加我微信了解详情" * 5)
    assert v.verdict == "reject"


def test_template_like_quarantined():
    text = ("岗位急招，速来岗位急招，速来\n") * 10
    v = validate_jd("招聘工程师", text)
    assert v.verdict == "quarantine"
