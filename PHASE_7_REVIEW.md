# Phase 7 Review —— Job Matching 验收与六维自检

> 2026-09-03 ｜ 执行计划：`docs/plans/2026-09-03-phase7-job-matching.md` ｜ 代码：342 测试全绿（288 存量 + 54 新增）｜ 零迁移 / 零新依赖 ｜ E2 基线 **pass**

## 0. 交付物清单

| 交付物 | 位置 | 说明 |
|---|---|---|
| scoring 纯函数 | `src/skillgap/match/scoring.py` | scoring 1.0.0：四维加权公式（§4.1 冻结版）/ 三组判定 / §4.3 中性守卫 + neutral_flags；零 skillgap 依赖（守卫测试锁定） |
| 服务层 | `src/skillgap/match/service.py` | match_score：SQL 装配（required_level 复用 gap-v1 单一事实源）→ match_result 落库留痕 |
| 解释层 | `src/skillgap/match/explanation.py` | 模板解释（默认，零 LLM）+ LLM 解释（可选）+ check_consistency 数字程序比对（M6 验收） |
| E2 评测器 | `src/skillgap/eval/e2.py` | 指标纯函数（手写 Spearman 平均秩/MAE/Jaccard/PRF）+ seed_eval2 + run_e2（物化 + eval_run 留痕） |
| CLI | `match-score` / `eval-e2` | 单岗匹配（--llm-explain 可选）；E2 种子/跑分 |
| 测试 | 4 个文件 +54 项 | scoring 23（单调性/对抗性/守卫）+ 指标 15（手算锚定）+ service/explanation 11 + runner 5 |
| 口径裁决 | `docs/DECISION_LOG.md` D-2026-09-03-14 | C1（soft_requirements 全空→恒中性）+ C2（校准纪律）+ D1-D10 |

## 1. 验收核验表（MVP M6 / ROADMAP Phase 7 逐条）

| 验收项 | 结果 | 证据 |
|---|---|---|
| E2 ρ ≥ 0.5 起步 | ✅ 远超 | **ρ = 0.8433**（pass 线 0.7）；MAE 9.38（≤12）；Jaccard 0.9822；三组 micro F1 0.9959；**Missing 组 F1 = 1.0**；verdict = pass（eval_run 留痕） |
| 单调性测试 100% | ✅ | test_match_scoring.py：level 单调（1→5 分数非降）+ conf 单调（0→1 非降） |
| 解释数字与 breakdown 一致（程序比对） | ✅ | check_consistency（正则数字 ⊆ breakdown 派生集）+ 模板测试通过 + LLM 不一致即抛 ExplanationInconsistency |
| 分数计算零 LLM（CI 静态检查） | ✅ | 守卫测试：scoring.py 无 skillgap import / 无 LLM 引用；服务层数值全部来自 SQL + 纯函数 |
| 对抗 1：裸声明分差显著 | ✅ | e2-001 vs e2-002（同 JD 同技能同等级）：conf 1.0 vs 0.3 → **分差 29.6**（≥10） |
| 对抗 2：无关 JD 上界 | ✅ | e2-003（P1 vs 算法岗）= 25.5 ≤ 29 |
| 对抗 3：别名变体一致性 | ✅ | e2-012（别名改写 JD，LLM 真实抽取物化）与 e2-008 **分数完全一致** →20.5 = alias 归一正确 |
| Huntr 四维对照 | ✅ | breakdown 四维 + neutral_flags + 三组覆盖状态 + 模板解释逐维拆解（含中性维度明示） |

## 2. E2 基线数字（2026-09-03，N=25 对，eval_run #1）

```json
{"spearman": 0.8433, "mae": 9.38, "jaccard": 0.9822,
 "prf_micro": {"f1": 0.9959}, "prf_missing": {"f1": 1.0},
 "macro_f1": 0.9814, "verdict": "pass",
 "adversarial": {"bare_claim_gap": 29.6, "unrelated_scores_max": 25.5,
                 "alias_scores_equal": true}}
```

跑分成本：1 次 LLM 调用（e2-012 别名 JD 物化，llm_cache 留痕）；e2-001 的 v2-16 文本与库内 job#16 content_hash 相同 → 自动去重复用（零 LLM）。

## 3. 六维自检

### Product —— 真的解决问题吗？
`match-score --candidate-id 3 --job-id 16` 一条命令输出"多少分、四维各多少、哪些达标/薄弱/缺失、为什么"。真实 e2e：39.0 分，RAG 达标（strong）、Python 薄弱（等级不足）、LangChain/PE/网络协议缺失——每个结论可回查画像与 JD 抽取。

### Engineering —— 过度设计了吗？
零迁移（match_result 表 Phase 2 已建）、零新依赖（Spearman/PRF 手写，无 scipy）；E2 runner 复用 E1 基建模式（evaluation_sample/eval_run）与 backfill_pending 管线；scoring 纯函数 190 行含软性匹配完整逻辑。

### AI —— LLM 被滥用了吗？
分数路径零 LLM（守卫测试锁定）；LLM 仅两处可选：解释文本（数字必须过程序比对，不一致即拦截降级）与 E2 物化的 1 次别名 JD 抽取（走既有 E1 管线+缓存）。

### Data —— 数字真实吗？
25 对全部真实库 JD + 5 个标注画像（技能已校验命中词表）；三组标注与库内 job_skill 逐对一致性校验通过（无漏标/多标）；物化走 content_hash 去重保证幂等。

### Evaluation —— 结果可验证吗？诚实记录三个已知限制：
1. **系统性低估**：残差分析显示 20/25 对系统分低于人分（最大 -41.5，e2-008）。根因是公式的二值满足性（D2：等级不达标 → ach_w=0），而人对"差一星达标"给部分分。排序正确（ρ=0.84）但绝对值偏保守。校准方向（需 DATA_MODEL 契约变更 + 升 1.1.0）：等级部分达标给比例 credit
2. **三组指标近完美的循环验证风险**：三组标注口径（D4 规则推导）与判定规则同构——jaccard 0.98 / F1 0.996 主要验证"实现与设计一致"，不是独立人判背书。有独立信息量的是分数维度（Spearman/MAE）
3. **同集标注无 held-out**：25 对全部参与评测，无独立测试集（EVALUATION_PLAN §3 未要求；v2 扩集时建议 20/5 分割）

### Resume —— 简历价值？
可展开的面试叙事：为什么 conf_factor 折减贡献不改满足性（证据薄≠不会，但贡献打折——与 gap 层星级差分离）；为什么解释数字必须程序比对（LLM 解释的自算数字是幻觉高发区）；为什么 E2 对抗用例要设计别名变体（评测抽取器归一化而非记忆）。

## 4. 真实 e2e（2026-09-03）

用户真实简历画像（candidate 3）vs 库内 job#16（AI 应用开发）：

- overall 39.0 / coverage 0.20 / importance_coverage 0.20 / evidence_quality 1.0（证据全扎实但覆盖面窄）/ experience_relevance 0.5（C1 中性）
- strong: RAG ｜ weak: Python（精通要求 vs L3）｜ missing: LangChain / Prompt Engineering / 网络协议

## 5. 下一步（Phase 8）

ROI 推荐（Demand×Gap÷Cost 纯函数）+ Career Planner Agent（LangGraph）。本阶段已备好原料：gap 的 demand/cost 字段 + match 的三组与 E2 基线；E2 残差分析（§3.1）可作为 potential_gain 校准输入。
