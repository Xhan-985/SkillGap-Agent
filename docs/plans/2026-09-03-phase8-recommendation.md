# Phase 8：Recommendation（M9，引入 LangGraph——ADR-006 复议点）实施计划

> **Goal**：ROI 优先级建议（roi-v1 纯公式）+ 项目推荐模板库 + Career Planner Agent（LangGraph 单 Agent，只读快照输入，解释输出带 Trace/回放）+ E3 评测基线（nDCG@5 / 数值正确性 / 引用真实性 / LLM-as-judge）。
> **Architecture**：三层——`recommend/roi.py` 纯函数（Demand×Gap÷Cost，零 LLM）；`recommend/service.py` 装配（gap-v1 聚合 + snapshot demand + 模板匹配 + recommendation 落库）；`recommend/agent.py` LangGraph 图（load 快照 → LLM 解释 → 程序校验 conditional edge → trace 落 llm trace）。E3 评测器复用 E1/E2 模式。
> **Tech Stack**：Python 3.12 + psycopg + pytest；**新依赖 langgraph**（首个 Agent 框架，ADR-006 冻结的引入时机）。

## Context

Phase 7 已交付 match scoring 1.0.0 + E2 基线 pass（ρ=0.8433）。Phase 6 gap-v1 已输出 demand/cost 原料（本阶段只消费不重算）。`recommendation` 表已建（零迁移）；`skill.learning_cost` 87 技能全覆盖（high 12 / mid 48 / low 27）；snapshot#4（china, N=201, high）可供应 demand。

公式（DATA_MODEL §4，Phase 1 冻结）：

```
cost_value(learning_cost) = low=1 ｜ mid=2 ｜ high=3        （§4.2 映射表）
potential_gain(s) = Demand(s) × Gap(s) ÷ Cost(s)             （roi-v1）
排序：potential_gain 降序 → priority_items（Top-K）
rationale：模板/LLM 生成但不得引入公式外数字（API §2.10 红线）
```

## 口径裁决（先落 DECISION_LOG，再动代码）

| # | 冲突/空白 | 裁决 |
|---|---|---|
| C1 | **Agent 必要性复议**（ADR-006 复议点 + ROADMAP 自检"若规则已达标记录复议结论"） | **引入**，定位=解释生成层：规则推荐（roi-v1）先行独立验收（任务 1-3 零 Agent 可用），Agent 仅消费只读快照产出个性化建议叙事 + 回答"为什么推荐它而非它"。数值 100% 规则计算（Agent 无改数权限——ADR-006 Decision 原文）。复议结论（规则已达标但引入仍成立：解释个性化是规则覆盖不了的场景）落 PHASE_8_REVIEW Engineering 维度 |
| C2 | EVALUATION_PLAN §4.2 要求 judge 与生成模型**不同源**，但项目唯一 LLM 通道是 DeepSeek | judge 用 `deepseek-reasoner`（同厂商不同模型——部分满足）；如实记录为已知限制。judge 本就定位 Warn 级信号不作 Block，风险可接受 |
| C3 | time_budget_days（7/14/30）语义：API §2.10 未定义其对排序的影响 | **不影响 ROI 排序**（potential_gain 与预算无关）；用于 project_suggestions 过滤（est_days ≤ time_budget_days）+ 落库。裁决理由：预算改变的是"能做什么"不是"什么最值" |
| C4 | **demand 口径空白**：API §2.10 request 只有 market（无 category），gap 的参照系未定义 | 需求侧 = market 全类目聚合（复用 D-2026-09-03-13 类目聚合规则，scope 从 category 扩为 market）：频次 ≥0.20 入清单、required_level 取 must 映射最大值（无 must 取 2）、demand = 最新快照 frequency + evidence_ref。Sample<30 → SAMPLE_INSUFFICIENT（demand 缺省明示，不臆造） |

## 冻结的设计决策

| # | 决策 |
|---|---|
| D1 | `ROI_VERSION = "roi-v1"`；`potential_gain = round(frequency × gap ÷ cost_value, 2)`；排序 potential_gain 降序、同分按 frequency 降序；Top-K（K=10）入 priority_items |
| D2 | gap 复用 `gap.gapcalc`（单一事实来源）；genuine/transferable 标注沿用（transferable 项 rationale 注明"已有相邻证据可迁移，成本低"） |
| D3 | rationale 默认**确定性模板**（四要素：需求频次/当前缺口/成本档/预算内可完成性——数字全部来自 item 字段）；Agent 模式生成个性化叙事但数字过程序比对（复用 Phase 7 check_consistency 模式：解释数字 ⊆ item 派生数字集） |
| D4 | 项目模板库：`data/project_templates.json`（人工策划，每条含 template_id/title/target_skills/est_days/cost/source）；匹配 = 缺口技能 ∩ target_skills（交集 ≥1），排序按交集大小 → est_days 升序；过滤 est_days ≤ time_budget_days；**source 字段必填**（标注策划依据，合规审计） |
| D5 | LangGraph 图（`recommend/agent.py`）：`load_context`（确定性：组装只读快照 JSON）→ `generate`（LLM：输入快照，输出建议叙事）→ `verify`（程序：check_consistency 数字比对）→ conditional edge（fail → `revise` 重生成一次 → fail → 降级模板；pass → END）。checkpoint 开启 → trace 可回放（同输入确定性部分一致 = M6 式验收） |
| D6 | **数值红线守卫**：roi.py 零 skillgap import + 零 LLM（源码级静态测试，同 gapcalc/scoring 先例）；agent.py 的 LLM 输出仅进 explanation 字段，priority_items 数字由 service 层规则产出 |
| D7 | E3 指标（手写，无 scipy）：nDCG@5（人工排序为 relevance，系统排序为待评——增益归一 2^rel−1/理想 DCG）；数值正确性（抽样重算 = 纯函数复算，100%）；引用真实性（解释数字 vs snapshot 程序比对，100%）；LLM-as-judge（rubric-v1 固定 5 点量表，judge=deepseek-reasoner，10 条人工复核锚定） |
| D8 | E3 标注集 `data/eval/e3_seed_v1.json`：复用 E2 五画像（P1-P5）→ 每画像人工 Top-5 相关性排序（0-4 相关性分）+ judge 样本；标注双人（user+claude）+ 同学抽标 ≥1 画像复核建议 |
| D9 | E3 runner（`eval/e3.py`）复用 E1/E2 模式：seed 入 `evaluation_sample(eval_type='recommendation')`（表已支持）；跑分入 eval_run；画像物化复用 e2 的 `_materialize_candidate`（e2_profile_id 标记） |
| D10 | RAG 引用层（pgvector + "哪些 JD 要求 MCP"）：**默认延后**——skill-evidence SQL 版已覆盖精确溯源，语义检索需求未达 ADR-006 式 >30% 触发线；复议结论落 PHASE_8_REVIEW（ADR-004 的"Phase 8 才建索引"不等于"Phase 8 必须建"） |

## 文件结构

```
src/skillgap/recommend/          # 新包
  __init__.py
  roi.py                         # 纯函数（守卫测试锁定）
  service.py                     # recommend：聚合 gap + demand + 模板 + 落库
  agent.py                       # LangGraph Career Planner（图 + checkpoint/trace）
src/skillgap/eval/
  e3.py                          # E3 评测器（nDCG@5 纯函数 + runner + judge）
data/project_templates.json      # 人工策划模板库（首批 ~12 条）
data/eval/e3_seed_v1.json        # E3 标注集（5 画像 × Top-5 排序）
src/skillgap/cli.py              # +recommend / +agent-plan / +eval-e3
tests/test_recommend_roi.py       # 纯函数（公式/排序/守卫）
tests/test_recommend_service.py   # 装配 + 落库（真实 PG）
tests/test_recommend_agent.py     # LangGraph 图（Fake LLM：trace/校验/降级）
tests/test_eval_e3.py             # nDCG 手算锚定 + runner 机制
docs/DECISION_LOG.md              # C1-C4 + D1-D10
PHASE_8_REVIEW.md                 # 六维自检 + E3 基线数字 + ADR-006 复议结论
```

依赖方向：`cli → recommend.service → {roi(纯), gap.service, stats, db}`；`cli → recommend.agent → recommend.service`（只读）；`cli → eval.e3 → recommend.service`；`roi.py` 零依赖。

## 关键签名

```python
# roi.py（纯函数）
ROI_VERSION = "roi-v1"
COST_VALUE = {"low": 1.0, "mid": 2.0, "high": 3.0}
MIN_FREQUENCY = 0.20            # 入清单阈值（与 gap 类目规则同源）
TOP_K = 10

def potential_gain(frequency: float, gap: int, cost: str) -> float

def compute_priority(gap_items: list[dict],    # gap-v1 聚合输出 + learning_cost
                     ) -> list[dict]
# → [{skill, frequency, sample_size, evidence_ref, gap, cost,
#     potential_gain, type(genuine/transferable)}] 排序后 Top-K

def render_rationale(item: dict, time_budget_days: int) -> str

# service.py
def recommend(conn, candidate_id: int, time_budget_days: int = 14,
              market: str = "china", k: int = TOP_K) -> dict
# 装配：gap 类目→market 聚合 + snapshot demand + 模板匹配 →
# recommendation 落库 → API §2.10 结构（formula_version: roi-v1）

# agent.py
def build_planner_graph(gateway)          # StateGraph + checkpoint
def run_planner(conn, candidate_id: int, time_budget_days: int,
               gateway) -> dict
# → {"advice": str, "trace": [...], "fallback": bool}

# eval/e3.py
def ndcg_at_k(system_rank: list[str], human_relevance: dict[str, int],
              k: int = 5) -> float
def run_e3(conn, gateway, dataset_version: str = "e3-v1") -> dict
# → {ndcg_5, numeric_accuracy, citation_consistency, judge_score,
#    verdict} + eval_run 留痕
```

## 任务分解（7 任务，Plan→Implement→Test→Review）

1. **roi 纯函数 + 守卫测试**（~15 项）：公式逐项（demand×gap÷cost 三档成本）、排序稳定性（同分按 frequency）、Top-K 截断、transferable 标注透传、rationale 模板数字一致性、守卫（零 skillgap import/零 LLM）、MIN_FREQUENCY 过滤
2. **项目模板库 + service 装配**（~12 项，真实 PG）：market 聚合 gap（复用 gap service，scope 扩 market）、demand 从最新快照、模板匹配（交集/est_days 过滤）、recommendation 落库断言、SAMPLE_INSUFFICIENT（N<30）、404
3. **CLI recommend**（~4 项）：`recommend --candidate-id N [--budget 14] [--market china]` → JSON（rc：404=1）；`--llm-explain` 留 Agent 任务后补测
4. **LangGraph Agent**（~10 项，Fake LLM）：图结构（load→generate→verify→conditional：revise/降级）、checkpoint trace 回放（同输入同 trace 确定性部分）、verify 拦截自算数字、降级模板不抛错、数值不被 LLM 污染（priority_items 字段逐项断言等于规则产出）
5. **E3 指标纯函数 + 标注集 + runner**（~12 项）：nDCG@5 手算锚定（已知值用例）、数值正确性复算、引用真实性比对、judge（rubric-v1 prompt 冻结 + deepseek-reasoner）、seed/物化复用 e2 模式
6. **E3 真实基线跑分**：seed 5 画像标注 → run_e3（规则推荐全量 + judge 5 样本 LLM 调用）→ 报告落 `data/eval/e3_report_v1.json` + eval_run 留痕；**验收**：nDCG@5 ≥0.5 起步（pass ≥0.7）；数值正确性 100%；引用一致性 100%；judge ≥3.0 起步（≥4.0 pass）——不达标走校准迭代（升 roi patch，留痕，≤2 轮）
7. **文档同步 + PHASE_8_REVIEW + 全量回归**：API §2.10 补 formula_version/neutral 语义；DECISION_LOG C1-C4/D1-D10；ADR-006 复议结论回填；ROADMAP/HANDOVER；全量回归（342 + ~53 ≈ 395 全绿）

## 验收对照（MVP M9 / ROADMAP Phase 8 / EVALUATION_PLAN §4）

| 验收项 | 覆盖 |
|---|---|
| E3 nDCG@5 ≥ 0.5 起步 | 任务 6 基线 |
| 数值正确性 100%（纯函数） | 任务 1 单测 + 任务 6 复算 |
| 解释引用与 snapshot 一致率 100% | check_consistency 程序比对（任务 4/5） |
| Agent 回放测试（同输入同 trace 确定性部分一致） | 任务 4 checkpoint 测试 |
| LLM 不参与指标计算（judge 仅解释文本） | D7 + runner 结构 |
| rationale 无公式外数字 | D3 模板 + 校验器 |
| potential_gain 100% 公式计算 | D6 守卫测试 |

## 风险

- **LangGraph 依赖引入**（首个重依赖）：锁 `langgraph>=0.2,<0.4`；若 API 破坏性变更，回退路径=手写三节点状态机（图逻辑仅 3 节点，撤除成本低——ADR-006 Reversibility）
- judge 同厂商限制（C2）——Warn 级定位 + 10 条人工复核锚定
- E3 标注只有 5 画像（每画像 1 条排序）——nDCG 样本薄；v2 扩画像（8-10 个）复验
- 模板库人工策划量：首批 12 条（覆盖词表高频缺口技能 Top-12）；质量>数量，source 必填
- 深度不确定性：DeepSeek reasoner 作 judge 的稳定性（超时/格式漂移）——失败样本跳过不中断，汇总报告明示 judge 覆盖率

## 验证

```powershell
cd "E:\codexproject\SkillGap Agent"
& .venv\Scripts\python.exe -m pytest tests/ -q --basetemp="E:\codexproject\SkillGap Agent\.pytest_tmp"
# 规则推荐（零 LLM）：
& .venv\Scripts\skillgap.exe recommend --candidate-id 3
# Agent 建议叙事（需 LLM_API_KEY）：
& .venv\Scripts\skillgap.exe agent-plan --candidate-id 3 --budget 14
# E3 基线：
& .venv\Scripts\skillgap.exe eval-e3
```
