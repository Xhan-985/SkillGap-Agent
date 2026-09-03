# Phase 7：Job Matching（M6）实施计划

> **Goal**：可解释匹配——确定性四维评分器（scoring_version 版本化）+ Strong/Weak/Missing 三组 + 模板/LLM 双模式解释（数字与 breakdown 程序比对一致）+ E2 标注集跑基线（Spearman/MAE/Jaccard/P/R/F1）。
> **Architecture**：三层——`match/scoring.py` 纯函数（零 LLM，守卫锁定，公式 DATA_MODEL §4.1 冻结版）；`match/service.py` SQL 装配 + match_result 落库；`match/explanation.py` 模板解释 + 数字一致性校验器（LLM 解释可选用同一校验器）。E2 评测器复用 E1 模式（evaluation_sample/eval_run + seed 入库 + CLI）。
> **Tech Stack**：Python 3.12 + psycopg + pytest（真实 PG）；指标手写实现（无 scipy 依赖）。

## Context

Phase 6 已交付 gap-v1（required_level 映射/星级差/classify 均可复用）。E2 标注集已就绪（`data/eval/e2_seed_v1.json`，25 对全标注，三组与库内 job_skill 逐对一致性校验通过，含 3 个对抗用例）。`match_result` 表、`evaluation_sample(eval_type='matching')`、`eval_run` 表均已建——**零迁移**。

公式（DATA_MODEL §4.1，Phase 1 冻结）：

```
required_weight(s) = 3 (must_have) / 1 (nice_to_have)
conf_factor(s)     = 0.5 + 0.5 × confidence(s)
coverage           = Σ ach_w / Σ req_w（ach_w = required_weight × conf_factor，满足时计入）
importance_coverage = Σ must_have 满足权重 / Σ must_have 总权重
evidence_quality   = mean(confidence of matched skills)
experience_relevance = 软性要求匹配率
Overall = 100 × (0.45×coverage + 0.25×importance_coverage
           + 0.20×evidence_quality + 0.10×experience_relevance)
```

## 口径裁决（先落 DECISION_LOG，再动代码）

| # | 冲突/空白 | 裁决 |
|---|---|---|
| C1 | DATA_MODEL §4 要求 experience_relevance 用 JD 侧 soft_requirements，但**真实库 201 条 JD 全部为空**（jd-analyze 管线未抽取存储，探测于 2026-09-03） | v1.0.0 **实现完整软性匹配逻辑**（年限≥/学历包含/语言包含→逐项匹配率，可评估项为 0 → 0.5 中性），但真实数据下恒走中性分支；如实标注 known limitation。回填需 E1 prompt 变更（走 E1 评测门禁），Phase 7 不做 |
| C2 | E2 校准与"同集评测"过拟合风险（25 对小样本） | 基线先跑 → 不达标才校准（每轮升 scoring_version patch 号，eval_run 留痕）；校准用同一集，**过拟合风险如实记录**（PHASE_7_REVIEW Evaluation 维度），v2 扩集后复验；指标变化 <3% 视为噪声（E1 小样本纪律沿用） |

## 冻结的设计决策

| # | 决策 |
|---|---|
| D1 | `SCORING_VERSION = "1.0.0"`（semver；权重/阈值/三组规则任一变更升 patch，E2 校准后升 minor） |
| D2 | **满足（计入 coverage 的 ach_w）⇔ actual_level ≥ required_level**；required_level 复用 `gap.gapcalc.required_level`（单一事实来源——Phase 6 已实现含 NULL 缺省/nice 封顶） |
| D3 | conf_factor 只折减贡献权重，**不改变满足性**（等级达标但证据薄 = 满足但贡献打折；与 gap 的 confidence 不进 gap 口径互补，共同构成 H1 修复的两面） |
| D4 | 三组判定（与 E2 标注口径对齐）：missing ⇔ 画像无记录；strong ⇔ 满足 ∧ confidence ≥ 0.5；weak ⇔ 有记录但不满足，或满足但 conf < 0.5（证据薄） |
| D5 | 除零守卫按 §4.3 中性 0.5 策略：Σreq_w=0 → coverage=0 + `invalid: no_skills` 标记；无 must → importance_coverage=0.5；无 matched → evidence_quality=0.5；软性不可评估 → 0.5。响应带 `neutral_flags` 数组明示哪些维度走了中性 |
| D6 | evidence_quality 的"matched skills" = JD 技能与画像有交集的技能（= strong ∪ weak 组），与三组口径同源 |
| D7 | explanation：默认**确定性模板**（数字 100% 来自 breakdown，含四维值/总分/三组计数与代表技能）；`--llm-explain` 可选走 jd gateway 生成（输入=breakdown JSON，禁止模型自算数字）；**一致性校验器**：正则抽取解释中全部数字，必须 ⊆ breakdown 派生数字集（M6 验收"程序比对一致"），LLM 失败降级模板（API §错误表既有约定） |
| D8 | 守卫：`scoring.py` 零 skillgap import + 零 LLM（同 gapcalc 先例，源码级静态测试锁定）；服务层数值全部来自 SQL + scoring 纯函数 |
| D9 | E2 runner（`eval/e2.py`）复用 E1 模式：`seed_eval2` 把 25 对入 `evaluation_sample(eval_type='matching')`；跑分入 `eval_run(eval_type='matching')`。**物化策略**——画像：candidate 以 `soft_profile.e2_profile_id` 标记 upsert（重复跑不重建）；JD：`job#N` 直接用库内岗；e2-012 别名 JD 走现有 ingest+extract 管线入库（content_hash 去重保证幂等，抽取 1 次 LLM 调用） |
| D10 | E2 指标（EVALUATION_PLAN §3.2，手写实现）：Spearman ρ（平均秩处理并列）、MAE、三组 Jaccard、micro P/R/F1（**Missing 组单独主报** + macro 辅助）；对抗三用例断言（裸声明分差 / 无关 ≤29 邻域 / 别名三组一致）；阈值 pass/warn/block 同表 |

## 文件结构

```
src/skillgap/match/            # 新包
  __init__.py
  scoring.py                   # 纯函数（守卫测试锁定）
  service.py                   # match_score：SQL 装配 + match_result 落库
  explanation.py               # 模板渲染 + check_consistency 数字一致性校验
src/skillgap/eval/
  e2.py                        # E2 评测器（seed_eval2 + run_e2 + 指标纯函数）
src/skillgap/cli.py            # +match-score / +eval-e2
tests/test_match_scoring.py    # 纯函数单测（公式/单调性/对抗/守卫）
tests/test_match_service.py    # 服务层（真实 PG + 落库断言）
tests/test_match_explanation.py # 模板/一致性校验
tests/test_eval_e2.py          # 指标纯函数 + runner 机制（Fake 物化）
docs/DECISION_LOG.md           # C1/C2 + D1-D10
PHASE_7_REVIEW.md              # 六维自检 + E2 基线数字
```

依赖方向：`cli → match.service → {scoring(纯), gap.gapcalc, db}`；`cli → eval.e2 → match.service`；`scoring.py` 零依赖。

## 关键签名

```python
# scoring.py（纯函数）
SCORING_VERSION = "1.0.0"
WEIGHTS = {"coverage": 0.45, "importance_coverage": 0.25,
           "evidence_quality": 0.20, "experience_relevance": 0.10}
REQUIRED_WEIGHT = {"must_have": 3.0, "nice_to_have": 1.0}
EVIDENCE_THRESHOLD = 0.5        # strong 判定线（与 gap-v1 同源）

def conf_factor(confidence: float) -> float   # 0.5 + 0.5*conf

def compute_match(reqs: list[dict],            # {skill, importance, required_level}
                  actual: dict[str, dict],     # {skill: {level, confidence}}
                  soft_pair: dict | None,      # {jd: [...], candidate: {...}}
                  ) -> dict
# → {"overall_score": float, "scoring_version": str,
#    "breakdown": {coverage, importance_coverage, evidence_quality,
#                  experience_relevance},
#    "strong_skills": [...], "weak_skills": [...], "missing_skills": [...],
#    "neutral_flags": ["no_must_have", ...], "invalid": None | "no_skills"}

# service.py
def match_score(conn, candidate_id: int, job_id: int, *,
                explain_llm: bool = False) -> dict
# 装配 reqs（job_skill + required_level）/actual（candidate_skill）/soft_pair
# （job.soft_requirements + candidate.soft_profile）→ compute_match →
# explanation → 落库 match_result → 返回 API §2.8 结构

# explanation.py
def render_template(result: dict) -> str
def check_consistency(explanation: str, result: dict) -> list[str]
# 返回不一致数字列表（空 = 通过；M6 验收 100%）

# eval/e2.py
def compute_metrics(pairs: list[dict]) -> dict
# [{system_score, human_score, system_groups: {strong,weak,missing},
#    human_groups: {...}}] → {spearman, mae, jaccard, prf_micro,
#   prf_missing, macro_f1, adversarial: {...}, verdict}
def seed_eval2(conn, dataset_path: str) -> int
def run_e2(conn, dataset_version: str, extractor=None) -> dict   # 入 eval_run
```

## 任务分解（6 任务，Plan→Implement→Test→Review）

1. **scoring 纯函数 + 守卫测试**（~18 项）：
   - 公式逐维：coverage（must/nice 权重 3:1、conf_factor 折减、不满足不计入）；importance_coverage（仅 must）；evidence_quality（matched 集均值）；experience_relevance（年限/学历/语言逐项 + 全中性 0.5）
   - Overall 权重和 = 100×Σ；round 到 1 位小数
   - **单调性（M6 验收）**：画像任一技能 level 提升 → overall 不降；conf 提升 → 不降
   - **对抗性 1（conf 折减）**：同技能同等级，conf 1.0 vs 0.3 → 分差显著（E2 e2-001/002 的分差来源）
   - 三组判定全分支（missing/满足∧conf≥0.5/满足但 conf<0.5/不满足）；与 gap-v1 EVIDENCE_THRESHOLD 同线
   - 中性守卫四分支 + invalid:no_skills；neutral_flags 正确
   - 守卫测试：scoring.py 无 `import skillgap`/`from skillgap`
2. **E2 指标纯函数**（~10 项）：
   - Spearman（含并列秩平均——手写秩相关）；MAE；Jaccard（三组并集）；micro P/R/F1 + Missing 单独 + macro
   - verdict 判定（阈值表）；对抗断言辅助（分差/上界/三组一致）
3. **match service + explanation**（~12 项，真实 PG）：
   - happy path：画像 vs 单岗 → 结构对齐 API §2.8（overall/breakdown/三组带 confidence/evidence_ref/scoring_version）
   - 落库断言：match_result 行存在且 breakdown/scoring_version 回读一致
   - e2-024 场景（无 must）→ importance_coverage=0.5 + neutral_flags；Σreq_w=0 → invalid
   - 404（candidate/job）；模板解释数字全部来自 breakdown（check_consistency 通过）
   - LLM 解释：Fake gateway 注入 → 生成走校验器；数字不一致 → 抛错标记；LLM 失败 → 降级模板
4. **CLI match-score + eval-e2**（~5 项）：
   - `match-score --candidate-id N --job-id M [--llm-explain]` → JSON
   - `eval-e2 [--seed-only] [--dataset data/eval/e2_seed_v1.json]`：seed_eval2 入库 → run_e2 跑分 → 打印报告 JSON（含 verdict）；--seed-only 只入库
5. **E2 基线跑分（真实数据 + 1 次 LLM 物化）**：
   - seed 25 对 → 物化画像（5 个）+ e2-012 别名 JD（走 ingest+extract，1 次 LLM 调用）
   - run_e2 全量跑 → 报告落 `data/eval/e2_report_v1.json` + eval_run 留痕
   - **验收判定**：ρ ≥ 0.5 起步（ROADMAP）；ρ < 0.5 或 MAE > 20 → 校准迭代（调权重/三组阈值，升 patch，重跑留痕；≤2 轮，更多则回 DECISION_LOG 复议）
6. **文档同步 + PHASE_7_REVIEW.md + 全量回归**：
   - API.md §2.8 补 neutral_flags/scoring_version 语义与模板解释约定；DECISION_LOG 落 C1/C2/D1-D10；ROADMAP Phase 7 完成状态；HANDOVER 更新（Phase 8 下一步）
   - 全量回归（288 + ~45 新 ≈ 333 全绿）

## 验收对照（MVP M6 / ROADMAP Phase 7）

| 验收项 | 覆盖 |
|---|---|
| E2 ρ ≥ 0.5 起步 | 任务 5 基线跑分（不达标走校准迭代留痕） |
| 单调性测试 100% | 任务 1（纯函数，能力提升→分数不降） |
| 解释中每个数字与 breakdown 一致（程序比对） | check_consistency + 任务 3 测试 |
| 分数计算零 LLM（CI 静态检查） | D8 守卫测试（scoring.py 源码级） |
| Strong/Weak/Missing | D4 三组规则 + E2 三组指标 |
| Huntr 四维可解释对照 | breakdown 四维 + neutral_flags + 模板解释逐维拆解 |

## 风险

- e2-012 别名 JD 依赖 E1 抽取对别名的归一化能力——若三组不一致属**真实信号**（词表 alias 缺口），记录为词表改进项而非评测失败
- C1 恒中性 0.5 使 experience_relevance 维度在 E2 中无区分度——10% 权重摊平全体分数，若拖累 ρ 属已知结构问题（校准时评估降权/剔除，升版本）
- 同集校准过拟合（C2）——小样本纪律：变化 <3% 不作为调参依据；v2 扩集复验
- LLM 物化 e2-012 需真实 LLM_API_KEY（1 次调用；失败可重试，content_hash 幂等）

## 验证

```powershell
cd "E:\codexproject\SkillGap Agent"
& .venv\Scripts\python.exe -m pytest tests/ -q --basetemp="E:\codexproject\SkillGap Agent\.pytest_tmp"
# 单岗匹配（零 LLM）：
& .venv\Scripts\skillgap.exe match-score --candidate-id 3 --job-id 16
# E2 基线（含 1 次 LLM 物化）：
& .venv\Scripts\skillgap.exe eval-e2
```
