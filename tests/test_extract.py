from skillgap.ingest.extract import (
    ManualSkillExtractor, alias_map_from_db, load_alias_map, locate_evidence,
    resolve_skill_id,
)
from skillgap.models import SkillAnnotation
from skillgap.taxonomy.seed import seed_taxonomy

JD = "岗位要求：熟悉 RAG 全链路，掌握 LangChain 与 LangGraph 编排，精通 Python。"


def test_alias_map_loads_and_resolves(clean_db):
    seed_taxonomy(clean_db)
    amap = load_alias_map(clean_db)
    # 大小写/别名/规范名均可归一
    assert resolve_skill_id("rag", amap) == resolve_skill_id("RAG", amap)
    assert resolve_skill_id("检索增强生成", amap) == resolve_skill_id("rag", amap)
    assert resolve_skill_id("langchain", amap) is not None
    assert resolve_skill_id("LangChain", amap) == resolve_skill_id("langchain", amap)
    assert resolve_skill_id("完全不存在的技能", amap) is None


def test_locate_evidence_strict():
    assert locate_evidence(JD, "熟悉 RAG 全链路") is True
    assert locate_evidence(JD, "并不存在的证据片段") is False


def test_locate_evidence_tolerates_width_and_case():
    assert locate_evidence("掌握ＲＡＧ技术栈", "掌握RAG技术栈") is True


def test_manual_extractor_passes_through(clean_db):
    anns = [
        SkillAnnotation(raw_name="RAG", importance="must_have",
                        intensity="熟悉", evidence_text="熟悉 RAG 全链路"),
        SkillAnnotation(raw_name="LangGraph", importance="nice_to_have",
                        evidence_text="LangGraph 编排"),
    ]
    result = ManualSkillExtractor(anns).extract(JD)
    assert [a.raw_name for a in result] == ["RAG", "LangGraph"]


def test_manual_extractor_rejects_unlocatable_evidence():
    anns = [SkillAnnotation(raw_name="RAG", importance="must_have",
                            evidence_text="原文没有这句话")]
    try:
        ManualSkillExtractor(anns).extract(JD)
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_alias_map_from_db_helper(clean_db):
    seed_taxonomy(clean_db)
    amap = alias_map_from_db(clean_db)
    assert "langgraph" in amap and "lang graph" in amap
