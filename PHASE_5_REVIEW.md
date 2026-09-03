# Phase 5 Review —— Candidate Profile 验收与六维自检

> 2026-09-03 ｜ 执行计划：`docs/plans/2026-09-03-phase5-candidate-profile.md` ｜ 代码：242 测试全绿（202 存量 + 40 新增）｜ 零新迁移 / 零新依赖

## 0. 交付物清单

| 交付物 | 位置 | 说明 |
|---|---|---|
| confidence 纯函数 | `src/skillgap/profile/confidence.py` | conf-v1：`min(1.0, Σᵢ w₍ᵢ₎ × 0.5^(i-1))`，零 LLM 依赖（守卫测试锁定） |
| 权重规则表（公开） | `docs/WEIGHT_RULES.md` | 权重表 + 公式 + 逐例演算 + 语义要点（ROADMAP 产出项） |
| 简历 Prompt v1 | `src/skillgap/profile/prompt.py` | 证据分级（detail/desc/bare）+ level 程度词映射 + soft_profile 抽取；与 E1 JD prompt 独立演进 |
| LLMResumeExtractor | `src/skillgap/profile/extractor.py` | 复用 Gateway/locate_evidence/重试模式；`parse_json_content` 公共化（llm_extractor.py 微重构，行为不变） |
| 服务层 | `src/skillgap/profile/service.py` | analyze_resume（替换式重分析 D1）/ get_profile / add_manual_skill（D5）/ delete_candidate；单事务 + rollback |
| Pydantic 契约 | `src/skillgap/models.py` | ResumeEvidence/ResumeSkillAnnotation/ResumeSoftProfile/ResumeExtraction |
| CLI | `skillgap resume-analyze / profile-get / profile-add-skill / candidate-delete` | 4 命令 |
| 3 冻结画像 | `tests/profile_fixtures.py` | A 项目细节丰富型 / B 裸声明型 / C 手动勾选型（ROADMAP 验收项） |
| 测试 | 4 个新测试文件 | confidence 9 项 + extractor 8 项 + service 17 项 + CLI 6 项 |

## 1. 验收核验表（ROADMAP Phase 5 逐条）

| 验收项 | 结果 | 证据 |
|---|---|---|
| 每技能输出证据片段 + confidence | ✅ | analyze_resume/get_profile 响应结构；test_profile_service.py（画像 A：RAG conf=1.0/Python 0.6） |
| 权重公式单测全覆盖（含"熟悉 RAG"→低分边界） | ✅ | test_profile_confidence.py 9 项：单条 bare_claim=0.3、双 bare=0.45、三 detail 截断 1.0、无序等价、空→0.0、守卫测试（源码零 LLM 依赖）、权重值域==DB CHECK |
| 3 个差异化画像测试用例固定 | ✅ | tests/profile_fixtures.py A/B/C（B 含 MVP"了解 MCP→0.3"验收锚点；C 含 D1 manual 保留全语义） |
| （产出项）证据识别三分类 | ✅ | Prompt v1 分级规则 + ResumeEvidenceTypeEnum；extractor 证据定位校验（不可定位即失败，重试≤2） |
| （产出项）手动勾选技能（manual 证据） | ✅ | add_manual_skill：整行替换、confidence=1.0、词表外拒绝（D5） |
| （产出项）confidence 纯函数 + 权重规则表公开 | ✅ | conf-v1 冻结；WEIGHT_RULES.md 含逐例演算（可手算复核） |

## 2. 设计决策（DECISION_LOG D-2026-09-03-11/12）

- **D4 confidence 公式**：证据权重降序 + 次数衰减 γ=0.5，封顶 1.0——满足"Σ(weight) 归一化 + 次数衰减"（DATA_MODEL §2.7），且与 candidate_evidence.weight 的 DB CHECK 严格一致
- **D1 替换式重分析**：简历=当前状态快照，resume_text 行整体替换；manual 行永不删（用户显式意图粘性）；冲突跳过 + notice（无数值损失——manual confidence 已 1.0）
- **D3 level 与 confidence 正交**："声明是 3 星，但系统只有 0.3 相信"= 声明 vs 证明的产品叙事；gap 用星级、match 用 conf_factor（H1 口径延续）
- **D2 evidence_ref**：分析会话内 `resume#L<n>` 行号，不落库（原文仅本会话保留）——API.md 已加澄清注

## 3. 六维自检

### Product —— 真的解决问题吗？
M5 闭环：简历粘贴 → 每技能证据链（类型/原文/权重）+ confidence + level。证据呈现可被"死亡追问"：每条证据带类型标签与原文片段、公式逐例演算可手算（WEIGHT_RULES.md 公开）、未归一词与 manual 冲突均显式 notice 不静默。缺口：真实简历 e2e 验证待用户实际使用反馈（本轮仅 MockTransport/Fake 替身验证逻辑层）。

### Engineering —— 过度设计了吗？
零新表（candidate 三表 Phase 2 已建）、零迁移、零新依赖。最大复用面：Gateway/Provider/locate_evidence/record_candidates/alias 归一全为既有代码；`parse_json_content` 公共化仅重命名不改行为（JD 抽取 7 项测试无回归）。profile.confidence 零依赖 + 守卫测试（沿用 stats.py 模式）。D1 替换式避免 schema 加 provenance 列的迁移成本——权衡已文档化。

### AI —— LLM 被滥用了吗？
LLM 只做两件事：证据分级抽取 + level 推断。confidence/权重/所有数值 100% 纯函数（守卫测试锁定 confidence.py 源码不含 llm/extract 引用）。LLM 输出经 Pydantic 校验 + 证据定位校验，失败重试≤2 后明示 ExtractionFailed，不降级不静默。

### Data —— 数字真实吗？
confidence 可手算复核（WEIGHT_RULES.md 逐例演算与单测一一对应）；权重值域与 DB CHECK 双向锁定。简历原文不落库（仅会话内计算行号）——隐私边界干净。词表外技能进 new_skill_candidate（first_seen_job_id NULL 可区分来源），不静默入画像。

### Evaluation —— 结果可验证吗？
conf-v1 同输入零漂移（纯函数）。3 冻结画像 A/B/C 作为回归锚点（fixture 独立文件，服务层/CLI 测试共享）。**已知限制（诚实记录）**：LLM level 推断无评测集背书（E2 属 Phase 7）——prompt 规则映射（了解=2/熟悉=3/熟练=4/精通=5）+ 手动勾选覆盖兜底；真实简历抽取质量待用户使用后按需建立 resume 评测集。

### Resume —— 简历价值？
"证据分三级、置信度可手算、声明和证明分开呈现——画像不是关键词匹配。" 面试可展开：为什么次数衰减 γ=0.5（防证据堆刷分）；为什么 level 与 confidence 正交（声明 vs 证明）；为什么重分析用替换式（简历=当前快照，陈旧证据不累积）。

## 4. 遗留与下一步

1. **Phase 6 Skill Gap**：岗位要求 vs 画像的差距量化（actual_level 已就绪——candidate_skill.level；transferable 判定需 skill_relations 数据）
2. **真实简历 e2e**：用户以自身简历跑 `resume-analyze`，验证 prompt v1 在真实简历上的抽取质量（可发现分级/level 推断偏差）
3. **PDF 输入**（后置）：需 ADR + pypdf 依赖，MVP 外 Should Have
4. **resume 评测集**（可选）：真实使用后若 level 推断偏差显著，建立 E-画像评测集（同 E1 模式：冻结标注 + F1）
