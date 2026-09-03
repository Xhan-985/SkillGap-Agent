# Phase 5：Candidate Profile（M5）实施计划

## Context

Phases 0-4 已完成（N=201 岗位、快照 #4、E1 双版本基线）。Phase 5 = 简历粘贴 → 证据化画像：每技能输出证据片段（project_detail/project_desc/bare_claim 分级）+ confidence（纯函数规则计算）+ LLM 推断 level（1-5 星，可手动覆盖）。用户已确认：**纯文本输入（无 PDF）**；**level = LLM 推断 + 手动覆盖**。

表结构已存在（migrations/001 L126-149 candidate/candidate_skill/candidate_evidence），**零迁移**。核心复用：LLM Gateway/Provider、`locate_evidence` 证据定位、alias 归一（`resolve_skill_id`/`record_candidates`）、`LLMSkillExtractor` 的"校验→重试→ExtractionFailed"模式。

## 冻结的设计决策

| # | 决策 |
|---|---|
| D1 | 重复分析为**替换式**：删该 candidate 全部 `source_type='resume_text'` 行后插入新结果；`manual` 行永不删；冲突技能跳过插入 + 显式 notice（manual_overridden） |
| D2 | `evidence_ref` = `"resume#L<n>"`（分析时算行号，尽力而为）；**不落库**，get_profile 返回 null（简历原文仅本会话保留） |
| D3 | bare_claim 的 level 照存 LLM 推断值（level 与 confidence 正交：声明 3 星但系统只 0.3 相信） |
| D4 | **confidence = min(1.0, Σᵢ w₍ᵢ₎ × 0.5^(i-1))**（权重降序排，次数衰减 γ=0.5，round 4 位）。单条 bare_claim=0.3（"熟悉 RAG"低分边界 ✓）；`CONFIDENCE_METHOD_VERSION="conf-v1"` |
| D5 | `add_manual_skill` 整行替换为 manual（confidence=1.0，evidence 缺省"手动勾选"）；词表外技能**拒绝**（不进 new_skill_candidate） |
| D6 | 简历长度校验 50–20000（对齐 jd-analyze） |

## 文件结构

```
src/skillgap/profile/          # 新包
  __init__.py
  confidence.py                # 纯函数，零 skillgap 依赖（守卫测试锁定）
  prompt.py                    # RESUME_PROMPT_VERSION="v1"（证据分级 + level 程度词映射规则）
  extractor.py                 # LLMResumeExtractor（复用 gateway + locate_evidence + 重试）
  service.py                   # analyze_resume / get_profile / add_manual_skill / delete_candidate
src/skillgap/models.py         # 追加 ResumeEvidence/ResumeSkillAnnotation/ResumeSoftProfile/ResumeExtraction
src/skillgap/extract/llm_extractor.py  # 微重构：_parse_content → 公共 parse_json_content
src/skillgap/ingest/extract.py        # 微重构：record_candidates job_id 类型放宽 int|None
src/skillgap/cli.py            # +4 命令
docs/WEIGHT_RULES.md           # 权重规则表（公开交付物，含逐例演算）
tests/test_profile_confidence.py / test_profile_extractor.py / profile_fixtures.py / test_profile_service.py
```

依赖方向：`cli → profile.service → {profile.extractor → llm.gateway → provider, ingest.extract}`；`confidence.py` 禁止 import llm/extract。

## 关键签名

```python
def compute_confidence(weights: Sequence[float]) -> float
class LLMResumeExtractor:
    def extract_full(self, resume_text: str) -> ResumeExtraction  # 失败抛 ExtractionFailed
def analyze_resume(conn, resume_text, extractor, candidate_id=None) -> dict
def get_profile(conn, candidate_id: int) -> dict          # CandidateNotFound
def add_manual_skill(conn, candidate_id, skill_name, level, evidence_text=None) -> dict
def delete_candidate(conn, candidate_id: int) -> bool
```

Resume 证据 schema：`ResumeEvidence{type: project_detail|project_desc|bare_claim, text}`；`ResumeSkillAnnotation{raw_name, level 1-5, evidences ≥1}`。未归一技能 → `new_skill_candidate`（first_seen_job_id NULL）+ notice 不静默。

## 任务分解（5 任务，每个 Plan→Implement→Test→Review）

1. **confidence 纯函数 + Pydantic 模型 + WEIGHT_RULES.md**：14 项单测（单条 bare=0.3、双 bare=0.45、封顶 1.0、无序等价、空→0.0、守卫测试：confidence.py 源码不含 skillgap.llm/extract、权重值域==DB CHECK）
2. **Resume Prompt v1 + LLMResumeExtractor**：8 项 MockTransport 测试（happy path/markdown 容忍/level 越界重试/证据不可定位重试失败/soft_profile 全 null/last_usage）
3. **服务层 + 3 个冻结画像 fixture**（FakeResumeExtractor，零 LLM）：
   - A 项目细节丰富型（RAG project_detail→conf 1.0；Python desc→0.6；soft_profile 齐）
   - B 裸声明型（"熟悉 RAG，了解 MCP"→各 0.3；soft_profile 全 null——MVP 验收项）
   - C 手动勾选型（add Python L5→conf 1.0；再 analyze→manual 保留 + notice）
   - ~17 项服务测试（创建/404/长度校验/别名落库/未归一 notice/替换语义/冲突跳过/级联删除/事务回滚/evidence_ref 行号）
4. **CLI 4 命令**：`resume-analyze --file [--candidate-id]`（无 key rc=2）/ `profile-get` / `profile-add-skill --skill --level [--evidence]` / `candidate-delete`
5. **文档同步 + PHASE_5_REVIEW.md**：ROADMAP/HANDOVER/API（evidence_ref 澄清）/UI_SPEC（0.45→0.3 修正）/DECISION_LOG（conf-v1 + 替换式语义）；落档 docs/plans/；全量回归（202+~41 新 ≈ 243 全绿）

## 验收对照

- 每技能证据片段 + confidence：响应结构 + 服务测试
- 公式单测全覆盖含"熟悉 RAG"→0.3：test_profile_confidence
- 3 个差异化画像固定：profile_fixtures.py A/B/C
- confidence 非规则外来源：纯函数 + 守卫测试 + WEIGHT_RULES.md 公开可手算

## 风险

- LLM level 无评测集背书（E2 属 Phase 7）→ prompt 规则 + fixture + 手动覆盖兜底，诚实记入 REVIEW 已知限制
- manual 冲突跳过仅损失证据展示不损失数值（confidence 已 1.0）
- E1 JD prompt 不动 → 无 eval-e1 回归义务（llm_extractor 仅重命名不改行为，全量测试覆盖）

## 验证

```powershell
cd "E:\codexproject\SkillGap Agent"
& .venv\Scripts\python.exe -m pytest tests/ -q --basetemp="E:\codexproject\SkillGap Agent\.pytest_tmp"
# 端到端（需 LLM_API_KEY）：
& .venv\Scripts\skillgap.exe resume-analyze --file resume.txt
& .venv\Scripts\skillgap.exe profile-get --candidate-id 1
```
