# Phase 6：Skill Gap（M7）实施计划

> **Goal**：岗位要求 vs 候选人画像的差距量化——纯函数 Gap 计算 + genuine/transferable 判定 + 最大缺口清单（带排序原料，供 Phase 7/8 消费）。
> **Architecture**：新增 `src/skillgap/gap/` 包：`gapcalc.py` 纯函数（零 skillgap 依赖，守卫测试锁定）+ `service.py`（SQL 装配，单岗 / 类目聚合双模式）。零 LLM、零迁移（表结构全就绪）。
> **Tech Stack**：Python 3.12 + psycopg + pytest（真实 PG 测试库）。

## Context

Phases 0-5 已完成（N=201、快照 #4、242 测试全绿、画像 A/B/C 冻结）。Phase 6 输入 = `job_skill`（岗位要求侧）+ `candidate_skill`（画像侧，Phase 5 产出），输出 = 可解释 Gap 报告。

表结构零迁移：`skill_relation(relation_type IN ('related','transferable_to'))` + 种子数据（Java↔Python、MySQL↔PostgreSQL transferable_to）已入库；`skill.parent_skill_id` 自引用已存在。

## 口径裁决（先落 DECISION_LOG，再动代码）

| # | 冲突 | 裁决 |
|---|---|---|
| C1 | ROADMAP Phase 6 产出写"含 confidence 折减"，DATA_MODEL §4.4（H1 修复）写"confidence 不直接进 gap" | **按 DATA_MODEL 裁决**：gap = 纯星级差；conf_factor 属 Phase 7 match 公式。ROADMAP 该行更新措辞 |
| C2 | API §2.9 类目聚合模式（`?category=`）无聚合规则定义 | **本计划冻结**（见 D4） |

## 冻结的设计决策

| # | 决策 |
|---|---|
| D1 | `required_level`：精通=5 ｜ 熟练=4 ｜ 熟悉=3 ｜ 了解=2（DATA_MODEL §4.2）；`intensity IS NULL` → must_have 取 3（熟悉中性档）、nice_to_have 取 2；nice_to_have 一律封顶 2 |
| D2 | `gap(s) = clamp(required_level − actual_level, ≥ 0)`；用户无该技能记录 → actual_level = 0（gap = required_level）。**confidence 不进 gap**（C1 裁决） |
| D3 | genuine/transferable 判定（DATA_MODEL §4.4 冻结规则）：缺口技能 s，其**相关技能集** = {s} ∪ {s 的 parent（沿 parent_skill_id 上溯一层）} ∪ {skill_relation(relation_type=transferable_to) 双向关联}。相关技能集中**存在** confidence ≥ 0.5 的画像记录 → `transferable`（note 取 relation.note 或 parent 说明）；**全部** confidence < 0.5 或无记录 → `genuine` |
| D4 | 类目聚合模式：类目内出现频次 ≥ 20%（`min_freq` 参数，默认 0.20）的技能进入要求清单；`required_level` = 该技能在此类目 must_have 行的映射最大值（无 must_have 行则取 2）；`demand` = frequency + sample_size + snapshot 引用（stats.py 口径） |
| D5 | 排序：gaps 按 gap 降序、同 gap 按 demand frequency 降序（稳定排序）。响应含 cost（learning_cost）与 demand 原料字段——ROI 公式（Demand×Gap÷Cost）属 Phase 8 roi-v1，本阶段只供原料不计算分值 |
| D6 | 零 LLM：全链路 SQL + 纯函数；`gapcalc.py` 源码禁止 import skillgap 任何模块（守卫测试锁定，对齐 confidence.py/stats.py 先例） |
| D7 | 版本标识 `GAP_METHOD_VERSION = "gap-v1"`（响应携带，后续口径变更可追溯） |
| D8 | 输出结构对齐 API §2.9：`{ candidate_id, mode, job_id|category, gaps: [{skill_id, required_level, actual_level, gap, type, demand, cost}], transferable: [{skill_id, via, note}], gap_version }` |

## 文件结构

```
src/skillgap/gap/            # 新包
  __init__.py
  gapcalc.py                 # 纯函数（守卫测试锁定）
  service.py                 # get_gaps(conn, candidate_id, *, job_id | category+market, min_freq)
src/skillgap/cli.py          # +1 子命令 gap-get
tests/test_gap_calc.py       # 纯函数单测（单调性 + 边界 + 守卫）
tests/test_gap_service.py    # 服务测试（真实 PG，fixture 复用 profile_fixtures 模式）
docs/DECISION_LOG.md         # C1/C2 裁决 + D1-D8
PHASE_6_REVIEW.md            # 验收六维自检
```

依赖方向：`cli → gap.service → {gapcalc(纯), stats, db}`；`gapcalc.py` 零依赖。

## 关键签名

```python
# gapcalc.py（纯函数，零 skillgap 依赖）
GAP_METHOD_VERSION = "gap-v1"
INTENSITY_LEVELS = {"精通": 5, "熟练": 4, "熟悉": 3, "了解": 2}

def required_level(importance: str, intensity: str | None) -> int
    # must_have: INTENSITY_LEVELS[intensity]，None→3；nice_to_have: min(映射值, 2)，None→2

def gap(required: int, actual: int) -> int
    # max(0, required - actual)；actual 缺省由调用方传 0

def classify(skills_with_evidence: dict[str, float],   # {skill_id: confidence}
             related_map: dict[str, set[str]],         # {skill_id: 相关技能集(含自身)}
             gap_skills: list[str]) -> dict[str, str]  # {skill_id: "genuine"|"transferable"}

# service.py
class CandidateNotFound(LookupError)   # 复用 profile.service 异常或独立定义
class JobNotFound(LookupError)

def get_gaps(conn, candidate_id: int, *, job_id: int | None = None,
             category: str | None = None, market: str = "china",
             min_freq: float = 0.20) -> dict
    # job_id 与 category 二选一（都给/都不给 → ValueError）
```

类目聚合 demand 原料复用 `stats.skill_frequency()`（S11 口径，零 LLM）+ 最近快照引用（`market_snapshot` 最新 high 行）。

## 任务分解（5 任务，每个 Plan→Implement→Test→Review）

1. **gapcalc 纯函数 + 守卫测试**（~14 项）：
   - required_level 映射全表（4 程度词 × must/nice × NULL = 10 例）；nice 精通封顶 2
   - gap：常规 / 负值 clamp 0 / required=actual→0 / actual=0 全额缺口
   - **单调性**（MVP 验收）：固定 required=4，actual 0→1→2→3→4，gap 严格非增且收窄到 0
   - classify：genuine（相关集全无证据）/ transferable（关联技能 conf=0.5 恰好达标、0.49 不达标）/ 自身有证据但已达标不进 gap / parent 链判定
   - 守卫测试：gapcalc.py 源码不含 `import skillgap` / `llm`
2. **服务层单岗模式**（~10 项，真实 PG + fixture）：
   - happy path：画像 B（裸声明型 conf=0.3）vs 高要求 JD → RAG genuine gap=required-0（画像 B 无 RAG？有——conf 0.3 但 level 3：gap 按星级差，type=genuine 当无关联证据）
   - Java 画像 conf≥0.5 vs 要求 Python 的 JD → transferable（note 带 relation.note）
   - 边界（MVP 验收）：**完全达标岗位** → gaps 为空列表；**完全无关岗位**（要求全词表冷门技能、画像零重叠）→ 全 genuine
   - 404：candidate / job 不存在；参数校验：job_id 与 category 互斥
   - intensity NULL 的 must_have 行 → required=3
3. **类目聚合模式**（~6 项）：
   - fixture 造 10 条同类目 job → 频次 ≥ 0.2 技能进清单、< 0.2 排除
   - required 取类目内 must_have 映射最大值；无 must_have 行 → 2
   - demand 原料：frequency/sample_size + snapshot 引用存在
   - min_freq 覆盖参数生效
4. **CLI `gap-get`**（~4 项）：
   - `gap-get --candidate-id N --job-id M` / `gap-get --candidate-id N --category ai_application_dev [--market china --min-freq 0.2]`
   - 输出 JSON 按规范排序（gap 降序、同 gap 按 frequency 降序）
   - 404 → stderr + rc=1；互斥参数 → rc=2
5. **文档同步 + PHASE_6_REVIEW.md**：
   - ROADMAP Phase 6 行措辞修正（C1）+ 完成状态；API.md §2.9 补 D4 聚合规则与 gap_version；DATA_MODEL §4.2 补 NULL→3 缺省；DECISION_LOG 落 C1/C2/D1-D8；HANDOVER 更新
   - 全量回归（242 + ~34 新 ≈ 276 全绿）

## 验收对照（MVP M7 / ROADMAP Phase 6）

| 验收项 | 覆盖 |
|---|---|
| 能力提升 → 缺口单调收窄（纯函数单测） | 任务 1 单调性测试 |
| 完全无关 / 完全达标边界用例 | 任务 2 |
| Gap 计算为纯函数 | gapcalc.py + 守卫测试 |
| transferable/genuine 区分 | 任务 1 classify + 任务 2 SQL 装配 |
| 最大缺口清单（带 ROI 排序接口） | D5 排序 + demand/cost 原料字段（Phase 8 固化 roi-v1） |

## 风险

- transferable 判定的 parent 上溯只走一层（词表 parent 层级浅，YAGNI；多层留待真实需求）
- 类目聚合的 20% 阈值是 heuristic 首值——D4 冻结为参数，E2/Phase 7 校准后升版本
- gap_report 不落库（每次实时计算，纯读）——Phase 9 若评测需要历史再考虑持久化

## 验证

```powershell
cd "E:\codexproject\SkillGap Agent"
& .venv\Scripts\python.exe -m pytest tests/ -q --basetemp="E:\codexproject\SkillGap Agent\.pytest_tmp"
# 端到端（零 LLM key 依赖）：
& .venv\Scripts\skillgap.exe gap-get --candidate-id 1 --job-id 1
& .venv\Scripts\skillgap.exe gap-get --candidate-id 1 --category ai_application_dev
```
