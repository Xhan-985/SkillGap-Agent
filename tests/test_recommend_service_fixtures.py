"""recommend 服务层测试夹具：种子市场数据（2 岗 + 画像 + 模板）。"""
import json
from pathlib import Path

from skillgap.models import (
    ResumeEvidence, ResumeExtraction, ResumeSkillAnnotation,
)
from skillgap.profile.service import analyze_resume
from tests.profile_fixtures import FakeResumeExtractor
from tests.test_schema import _insert_job, _job_kwargs, _source

TEMPLATES = [
    {"template_id": "t-mcp-agent", "title": "MCP 工具型 Agent 实战",
     "target_skills": ["MCP", "Python"], "est_days": 10,
     "cost": "mid", "source": "策划：基于词表高频缺口 MCP"},
    {"template_id": "t-rag-sys", "title": "RAG 检索系统搭建",
     "target_skills": ["RAG", "Docker"], "est_days": 20,
     "cost": "mid", "source": "策划：RAG 类岗位高频要求"},
    {"template_id": "t-docker-ci", "title": "容器化部署入门",
     "target_skills": ["Docker"], "est_days": 5,
     "cost": "low", "source": "策划：工程化基础"},
]

_PROFILE = ResumeExtraction(
    skills=[
        ResumeSkillAnnotation(raw_name="RAG", level=4, evidences=[
            ResumeEvidence(type="project_detail", text="课程项目搭建检索链路"),
        ]),
        ResumeSkillAnnotation(raw_name="Python", level=3, evidences=[
            ResumeEvidence(type="project_desc", text="日常脚本开发"),
        ]),
    ],
)

_FULL_PROFILE = ResumeExtraction(
    skills=[
        ResumeSkillAnnotation(raw_name=f, level=5, evidences=[
            ResumeEvidence(type="project_detail", text=f"{f} 实战经验"),
        ]) for f in ("MCP", "RAG", "Docker", "Python")
    ],
)


def write_templates(tmp_path, data=None):
    p = Path(tmp_path) / "p8_templates.json"
    p.write_text(json.dumps(data or TEMPLATES, ensure_ascii=False),
                 encoding="utf-8")
    return str(p)


def seed_market(clean_db, profile=None):
    """32 岗市场 + 画像 → candidate_id（N≥30 过 ADR-008 守门）。

    岗位构成：2 岗带技能要求（MCP/Python/RAG/Docker 口径同前）+ 30 岗
    空技能填充（不动频次分子）。频次：RAG 2/32≈0.0625 —— 注意低于
    0.20 阈值；为保证缺口技能入清单，2 岗外再补 14 岗各带全部 4 技能
    → MCP 16/32=0.5 / 其余 16/32=0.5。
    """
    sid = _source(clean_db)
    jids = []
    for i in range(32):
        jids.append(_insert_job(
            clean_db,
            **_job_kwargs(sid, content_hash=f"h-p8-{i}",
                          job_category="agent_dev")))
    # 岗 0：MCP 精通 + Python 熟悉；岗 1：RAG 熟练 + Docker 熟悉
    reqs = [(jids[0], "MCP", "must_have", "精通"),
            (jids[0], "Python", "must_have", "熟悉"),
            (jids[1], "RAG", "must_have", "熟练"),
            (jids[1], "Docker", "nice_to_have", "熟悉")]
    # 岗 2-15：全技能（频次到 16/32 = 0.5）
    for jid in jids[2:16]:
        reqs += [(jid, "MCP", "must_have", "熟悉"),
                 (jid, "Python", "must_have", "熟悉"),
                 (jid, "RAG", "must_have", "熟悉"),
                 (jid, "Docker", "nice_to_have", "熟悉")]
    for jid, skill, imp, inten in reqs:
        skl = clean_db.execute(
            "SELECT id FROM skill WHERE canonical_name=%s",
            (skill,)).fetchone()["id"]
        clean_db.execute(
            """INSERT INTO job_skill (job_id, skill_id, importance,
               intensity, evidence_text, extracted_by)
               VALUES (%s, %s, %s, %s, %s, 'manual')""",
            (jid, skl, imp, inten, f"要求 {skill}"))
    clean_db.commit()
    res = analyze_resume(clean_db, "画像市场测试" * 10,
                          FakeResumeExtractor(profile or _PROFILE))
    return res["candidate_id"]
