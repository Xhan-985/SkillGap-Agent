from skillgap.extract.prompt import (
    PROMPT_VERSION, SYSTEM_PROMPT, extraction_messages,
)


def test_prompt_version_frozen():
    assert PROMPT_VERSION == "v1"


def test_messages_wrap_jd_text():
    msgs = extraction_messages("岗位职责：负责 RAG 开发")
    assert msgs[0]["role"] == "system"
    assert "JD 技能抽取器" in msgs[0]["content"]
    assert "evidence_text" in msgs[0]["content"]
    assert msgs[1]["role"] == "user"
    assert "负责 RAG 开发" in msgs[1]["content"]


def test_prompt_declares_evidence_discipline():
    """证据可溯纪律必须在 Prompt 内声明（E1 硬要求）。"""
    assert "字符串定位校验" in SYSTEM_PROMPT
    assert "json_object" not in SYSTEM_PROMPT   # response_format 在 provider 层
