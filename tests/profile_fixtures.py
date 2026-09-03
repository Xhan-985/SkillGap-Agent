"""3 个冻结差异化画像 fixture（ROADMAP Phase 5 验收项——服务层测试共享）。

A 项目细节丰富型 / B 裸声明型（MVP"了解 MCP→低分"验收）/ C 手动勾选型。
配合 FakeResumeExtractor 使用——服务层测试零 LLM。
"""
from skillgap.models import (
    ResumeEvidence, ResumeExtraction, ResumeSkillAnnotation,
    ResumeSoftField, ResumeSoftProfile,
)


class FakeResumeExtractor:
    """直返预设 ResumeExtraction（服务层测试替身，零 LLM）。"""

    def __init__(self, extraction: ResumeExtraction):
        self._extraction = extraction
        self.last_usage: dict = {}

    def extract_full(self, resume_text: str) -> ResumeExtraction:
        return self._extraction


# ---- 画像 A：项目细节丰富型 ----

RESUME_A = (
    "张三，两年后端开发经验，本科软件工程专业。\n"
    "项目一：电商搜索系统，采用 pgvector+Hybrid Search+RRF+Rerank 搭建检索链路，召回率提升 18%。\n"
    "项目二：公司知识库项目，负责 Python 后端接口开发。\n"
)

EXTRACTION_A = ResumeExtraction(
    skills=[
        ResumeSkillAnnotation(raw_name="RAG", level=4, evidences=[
            ResumeEvidence(type="project_detail",
                           text="pgvector+Hybrid Search+RRF+Rerank 搭建检索链路"),
        ]),
        ResumeSkillAnnotation(raw_name="Python", level=3, evidences=[
            ResumeEvidence(type="project_desc", text="负责 Python 后端接口开发"),
        ]),
    ],
    soft_profile=ResumeSoftProfile(
        experience_years=ResumeSoftField(value=2,
                                         evidence_text="两年后端开发经验"),
        education=ResumeSoftField(value="本科·软件工程",
                                  evidence_text="本科软件工程专业"),
        languages=None,
    ),
)

# ---- 画像 B：裸声明型（MVP 验收："了解 MCP"→低分边界）----

RESUME_B = (
    "李四，应届毕业生，求职意向 AI 应用开发工程师。\n"
    "熟悉 RAG。\n"
    "了解 MCP。\n"
    "在校期间完成多项课程设计，无企业项目经历。\n"
)

EXTRACTION_B = ResumeExtraction(
    skills=[
        ResumeSkillAnnotation(raw_name="RAG", level=3, evidences=[
            ResumeEvidence(type="bare_claim", text="熟悉 RAG"),
        ]),
        ResumeSkillAnnotation(raw_name="MCP", level=2, evidences=[
            ResumeEvidence(type="bare_claim", text="了解 MCP"),
        ]),
    ],
    soft_profile=ResumeSoftProfile(),
)

# ---- 画像 C：手动勾选型 ----

RESUME_C = (
    "王五，应届毕业生，求职意向为数据方向岗位，在校期间完成多项课程设计。\n"
    "课程设计均为独立完成，无企业实习经历，无开源项目贡献。\n"
)

EXTRACTION_C = ResumeExtraction(skills=[], soft_profile=ResumeSoftProfile())

RESUME_C2 = (
    "王五，应届毕业生，求职意向为数据方向岗位，在校期间完成多项课程设计。\n"
    "课程项目：用 Python 完成数据分析课程作业，包含数据清洗与可视化部分。\n"
)

EXTRACTION_C2 = ResumeExtraction(
    skills=[
        ResumeSkillAnnotation(raw_name="Python", level=2, evidences=[
            ResumeEvidence(type="project_desc", text="用 Python 完成数据分析课程作业"),
        ]),
    ],
    soft_profile=ResumeSoftProfile(),
)
