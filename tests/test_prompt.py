from skillgap.extract.prompt import (
    PROMPT_VERSION, SYSTEM_PROMPT, extraction_messages,
)


def test_prompt_version_frozen():
    """v2（2026-09-02）：evidence 不跨列表符/换行——E1 v2 捕获的缺陷修复。"""
    assert PROMPT_VERSION == "v2"


def test_messages_wrap_jd_text():
    msgs = extraction_messages("岗位职责：负责 RAG 开发")
    assert msgs[0]["role"] == "system"
    assert "技能抽取器" in msgs[0]["content"]
    assert "evidence_text" in msgs[0]["content"]
    assert msgs[1]["role"] == "user"
    assert "负责 RAG 开发" in msgs[1]["content"]


def test_prompt_declares_evidence_discipline():
    """证据可溯纪律必须在 Prompt 内声明（E1 硬要求）。"""
    assert "字符串定位校验" in SYSTEM_PROMPT
    assert "不得跨越列表符号" in SYSTEM_PROMPT   # v2：跨行证据缺陷修复
    assert "json_object" not in SYSTEM_PROMPT   # response_format 在 provider 层
