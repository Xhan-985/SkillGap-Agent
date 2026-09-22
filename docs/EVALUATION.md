# EVALUATION —— 评测体系（README 级总览）

> 本文档是评测资产的入口：三层评测地图、冻结版本宣告、阈值、基线、方差、
> 演练、CI 集成、失败分诊与诚实边界。方案口径（指标定义/标注集设计）见
> `EVALUATION_PLAN.md`（Phase 1 冻结版）；实施细节见 `docs/plans/2026-09-04-phase9-evaluation-consolidation.md`。

## 1. 三层评测地图

| 层 | 评测 | 对象 | 依赖 LLM | eval_type | 位置 |
|---|---|---|---|---|---|
| E1 | 技能抽取 | JD → 技能列表 | 是（被测件） | `skill_extraction` | `src/skillgap/eval/e1.py` |
| E2 | 岗位匹配 | 匹配分 vs 人工分 | 否（零 LLM 跑分） | `matching` | `src/skillgap/eval/e2.py` |
| E3 | 学习推荐 | Top-5 排序 vs 标注相关性 | 否（judge 可选） | `recommendation` | `src/skillgap/eval/e3.py` |
| E5 | 数据质量 | 管道门禁指标 | 否 | `data_quality` | 观测信号，**不进门禁** |
| — | LLM-as-judge | 推荐解释质量 | 是（评审者） | 附在 E3 metrics | Warn 级参考，**永不进门禁** |

判定语义：`pass` / `warn`（不阻断，stderr 提示）/ `block`（阻断合并）。
**judge 分数永不进门禁**（rubric-v1 是参考信号，D-2026-09-04-16）。

## 2. 评测集 v1 冻结宣告（2026-09-08，Phase 9 D7）

| 评测集 | 版本 | 规模 | 判定依据快照 | 文件 |
|---|---|---|---|---|
| E1 抽取标注集 v1 | `e1_seed_v1` | 20 JD（混合中英） | — | `data/eval/e1_seed_v1.json` |
| E1 抽取标注集 v2 | `e1_seed_v2` | 53 真实 JD | — | `data/eval/e1_seed_v2.json` |
| E2 匹配标注集 | `e2-v1` | 25 对（5 画像 × 真实库 JD） | market snapshot #4（china N=201） | `data/eval/e2_seed_v1.json` |
| E3 推荐标注集 | `e3-v1` | 5 画像（复用 E2 画像） | 同上 | `data/eval/e3_seed_v1.json` |

> 判定依据快照列为冻结时点记录；2026-09-22 数据卷事故后库内快照重建为
> #1（N=202），三评测重跑全部落基线带内（见 §4 与 DATA.md §6）。

**冻结纪律**（EVALUATION_PLAN §6）：新用例进 v2，不静默修改 v1；修标注
须 `dataset_version+1` 并全量重跑。词表与评测集一致性由 CI 测试锚定
（`test_eval_determinism.py`，文件级检查不触 DB）。

**开放项（如实记录）**：E3 标注双人复核（user 复核 + 同学抽标 ≥1 画像）
未完成——不阻塞本阶段，已知偏差（"Python 补到精通" 系统性偏差 / 新手画像
成本项冲突）见 `data/eval/e3_report_v1.json`，为 v2 校准候选。

## 3. 阈值（跑分前冻结，单一事实来源在各评测器模块）

| 评测 | 指标 | pass | warn | block | 特殊规则 |
|---|---|---|---|---|---|
| E1 | F1 且 recall | ≥0.85 | ≥0.75 | 其余 | **evidence_rate <1.0 一票 block** |
| E2 | Spearman ρ | ≥0.7 | ≥0.5 | 其余 | 四指标（ρ/MAE≤12/20/Jaccard/PRF）综合判定，任一跌破即降级 |
| E3 | nDCG@5 | ≥0.5 | ≥0.35 | 其余 | 起步线（薄样本 5 画像） |
| judge | 5 点量表 | —（参考） | — | — | Warn 级不参与 verdict，失败跳过不中断 |

## 4. 基线（当前最新 run，全历史见 `skillgap eval-report`）

> 2026-09-22 数据卷事故后 eval_run 表重建为 4 条（历史 14 条的数值存档于
> `data/eval/*.json` 与本节历史基线行；重建过程与稳健性结论见 DATA.md §6 /
> DECISION_LOG D-2026-09-22-20）。

| 评测 | eval_run | 版本三元组 | 关键指标 | verdict |
|---|---|---|---|---|
| E1 | #1 | e1_seed_v2 / prompt v2 / deepseek-chat | F1=0.8644 / recall=0.8173 / evidence=1.0 / failures=0（N=53） | warn |
| E2 | #4 | e2-v1 / scoring 1.0.0 / deterministic | ρ=0.8277 / MAE=9.67 / Jaccard=0.9667（N=25） | pass |
| E3 | #3 | e3-v1 / roi-v1 / deterministic | nDCG@5=0.6497 / hit@3=1.0 / coverage=0.95（N=5） | pass |
| E2 | #2 | e2-v1 / scoring 1.0.0 / deterministic | ρ=0.445——**评测集 id 引用漂移缺陷的真实拦截案例**（库重建后 `job#N` 引用错位；修复 e90c76b 改内容寻址，重跑 #4 恢复带内） | block（留档） |

**历史基线（事故前存档）**：E1 #14 F1=0.8628 warn / E2 #7 ρ=0.8433 pass /
E3 #9 nDCG=0.6497 pass / judge #9 内附 rubric-v1 mean=5.0（参考不门禁）；
#10-12 为 T6 方差演练轮、#13 缓存复现轮（§6）。重建后各评测与历史基线同水位
（E1 +0.0016 / E2 -0.0156 / E3 持平）——**评测结论对数据重建稳健**。

当前 gate：**warn**（E1 warn + E2/E3 pass → exit 0）。

## 5. 工具链

```bash
skillgap eval-e1 --dataset-version e1_seed_v2   # E1 跑分（需 LLM_API_KEY）
skillgap eval-e2                                # E2 跑分（标注集自动入库）
skillgap eval-e3 [--judge]                      # E3 跑分（--judge 需 key，Warn 级）
skillgap eval-gate [--run-id N]                 # 汇总门禁：block→exit 1；--run-id 时点回放
skillgap eval-report [--out P]                  # Markdown 报告：版本三元组/差异/时间序列/诚实边界
```

报告差异计算**同版本优先**（dataset+prompt 相同的上一条；无则紧邻并标注
"跨版本，谨慎解读"）——跨版本差异含口径变化，不能归因系统好坏。

测试锚定（进 CI）：零漂移（E2/E3 双跑 metrics 完全相等）、taxonomy 一致性
（三份标注集 ⊆ 词表）、劣化演练（改坏权重 → ρ 崩 → gate block——见 §7）。

## 6. E1 方差（T6 演练 2026-09-08，`data/eval/e1_variance_v1.json`）

**协议**（C5）：3 轮全量重跑，每轮先 `TRUNCATE llm_cache`（**清缓存防零方差
假信号**——缓存会把上一轮的失败原样复现，#13 即为缓存复现轮：指标与 #12
逐位相同）。口径：F1 差异 <3%（绝对百分点）视为噪声级（§61）。

| 轮 | F1 | recall | failures | verdict |
|---|---|---|---|---|
| 1 | 0.8326 | 0.7640 | 2 | block |
| 2 | 0.8471 | 0.7944 | 1 | block |
| 3 | 0.8451 | 0.7893 | 1 | block |

**结果：极差 0.0145 < 0.03 → PASS**（噪声级以内），中位数 0.8451。

**发现（如实记录）**：
1. 三轮 verdict 均 block——非 F1 阈值触发（f1/recall 在 warn 区间），而是
   `evidence_rate<1.0` 一票 block 被 LLM 瞬时失败触发（每轮 1-2 个失败样本
   ≈1.9%-3.8% 失败率）。**E1 verdict 对 LLM 服务可用性敏感**；历史基线的
   warn 依赖 failures=0 的条件（#14 恢复轮：failures=0 → warn，F1=0.8628
   与基线同水位）。
2. vs 基线 0.8669 偏移约 -2.5pp，主因失败样本计空抽取拉低 recall。
3. 归因：DeepSeek 服务端波动（轮 3 耗时 678s，较前两轮 317/313s 翻倍）。

## 7. 劣化演练（"评测不是装饰"的证明）

**轨①自动化**（`test_eval_determinism.py`，进 CI）：monkeypatch 改坏
`scoring.WEIGHTS`（coverage→0，**不升版本**——模拟不升版的坏 PR）→
run_e2 → 排序翻转（ρ≈-0.866）→ verdict=block → gate 整体 block exit 1；
反向对照（不改权重同路径 pass exit 0）防测试自欺。

**轨②真实库**（T6 意外获得的真实案例，强于人为演练）：DeepSeek 瞬时失败
→ E1 #10-12 真实 block → `eval-gate` 真实 exit 1（E2/E3 pass 在场仍拦——
"任一 block → 整体 block"规则在**真实**劣化下验证）→ failures=0 重跑
（#14）恢复 warn。完整链路：劣化发生 → 门禁拦截 → 定位（§6 归因）→
恢复——这正是 §8 分诊表的 Flaky 处置路径走了一遍。

## 8. CI 集成（`.github/workflows/ci.yml`，C1/C2 分层裁决）

- **PR + push master**：test job 全量 pytest（514 项：三评测器 fixture 全链路 + 零漂移
  + taxonomy + 劣化演练 + API 契约）+ db-upgrade 迁移预检；pgvector 服务容器；
  docker job 仅构建镜像不推送（Phase 11 T6/C6，与 test 并行不阻塞）
- **E1 dispatch**：仅 `workflow_dispatch` 手动触发（key 泄露/费用/flaky 不进
  PR）；无 `secrets.LLM_API_KEY` 时 skip 并打印原因
- **首跑绿**（Phase 9 收口遗留项闭环）：run 35686447520 @ 6b1d277——test
  completed success，e1 skipped 属正常（非 dispatch 触发）
- **全量基线评测留本地**（C1 工程化适配）：真实市场数据（201 岗）与 LLM
  key 都在本地，CI 无法触达且仓库不分发数据——eval_run 是 source of
  truth，gate/report 离线读库工作且被单测锚定

## 9. 失败分诊（EVALUATION_PLAN §7 的本仓库具体化，D8）

| 分诊类别 | 本仓库处置 |
|---|---|
| Blocker（指标跌破 Block 线） | gate exit 1 阻断；定位四源（Prompt/Schema/词表/公式）；E2 公式类改动须升 scoring_version 全量重跑 |
| 可接受回归（切片降总量达标） | 豁免理由 + 复查触发条件写 eval_report 边注（暂无先例） |
| Flaky（LLM 输出方差） | 同版本重跑 3 次取中位；方差写报告（§6 协议：每轮清 llm_cache）；E1 evidence_rate 一票 block 对瞬时失败敏感——先查 `extraction_failures` 区分服务波动与真实回归 |
| 数据问题（标注错误） | 修标注 → dataset_version+1 → 全量重跑（e3-v1 已知偏差走此路径进 v2，不回改冻结集） |
| 覆盖缺口（无对应用例） | 生产/用户坏例 → 转回归用例（case promotion）；对抗用例库在 e2-v1（裸声明/无关 JD/别名变体） |

## 10. 诚实边界（§9 纪律 + Phase 9 增补）

1. **规模**：E1 N=53 / E2 N=25 / E3 N=5——只支撑**相对比较**（版本间回归），
   不支持绝对能力宣称；文档不得写"准确率 85%"类宣传语，必须附 N 与版本
2. **跨版本对比**：差异仅在版本三元组一致时有意义（见 §5 同版本优先规则）
3. **E1 非确定性**：temperature=0 非严格确定性承诺，同版本重跑允许 ≤3%
   极差（实测 1.45%，§6）；瞬时失败会让 verdict 在 warn/block 间跳变——
   看 verdict 前先看 `extraction_failures`
4. **judge 参考信号**：rubric-v1 均分 5.0 是对规则模板输出的评审（无幻觉
   空间），满分符合预期；区分度待 v2 评 Agent 叙事时体现——不是 rubric
   失效信号
5. **中文技能抽取无公开标注基准**（开源研究结论）——本评测集本身是可
   开源贡献的资产
