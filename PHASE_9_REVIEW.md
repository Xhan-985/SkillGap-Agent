# Phase 9 Review —— Evaluation 汇总（系统级）验收与六维自检

> 阶段：评测体系化收口——gate 汇总门禁 / 报告生成 / CI 首个 workflow /
> 劣化演练双轨 / 零漂移与 taxonomy 锚定 / E1 方差演练 / EVALUATION.md。
> 计划：`docs/plans/2026-09-04-phase9-evaluation-consolidation.md`（口径裁决
> C1-C5 + 冻结决策 D1-D8）。
>
> **补注（2026-09-24 Phase 11 T9 收口核对）**：本文"CI 首跑绿待 push"
> 遗留项已闭环——Phase 9 于 2026-09-22 push 后远端首跑绿
> （run 35686447520 @6b1d277：test completed success；e1 skipped 属
> 正常——dispatch 专属 job 无 secret 时跳过）。§1/§5 相关行按此读。

## 0. 交付物清单

| # | 交付 | 位置 | commit |
|---|---|---|---|
| T1 | gate 纯函数 + latest_runs 时点回放 + `eval-gate` CLI | `src/skillgap/eval/gate.py` + `tests/test_eval_gate.py`（14 测试） | 8fc8acc |
| T2 | 劣化演练自动化（monkeypatch 权重 → ρ 崩 → gate block；反向对照防自欺） | `tests/test_eval_determinism.py` | fc10c0e |
| T3 | 报告生成：四段 Markdown + `eval-report` CLI | `src/skillgap/eval/report.py` + `tests/test_eval_report.py`（13 测试） | 43edd37 |
| T4 | 零漂移双跑 + taxonomy 一致性（文件级，CI 无库可跑） | `tests/test_eval_determinism.py`（+4） | 9bef842 |
| T5 | CI 首个 workflow（PR 快检 + E1 dispatch） | `.github/workflows/ci.yml` | 302e622 |
| T6 | E1 方差演练（3 轮清缓存真跑，极差 0.0145 PASS） | `data/eval/e1_variance_v1.json` | c2691cf |
| T7 | EVALUATION.md（README 级）+ 本 Review + 文档同步 | `docs/EVALUATION.md` | 本 commit |

测试：443 全绿（Phase 8 收口 394 → +49）。

## 1. 验收核验表（对照 ROADMAP Phase 9 + 计划验收清单）

| 验收项 | 结果 | 证据 |
|---|---|---|
| 同版本重跑确定性指标零漂移 | ✅ | `test_run_e2/e3_zero_drift_double_run`：双跑 metrics dict 完全相等（E2 加验库内 JSONB 回读一致；E1 排除由方差演练覆盖） |
| LLM 指标方差 ≤3% | ✅ **PASS** | T6 实测极差 0.0145 < 0.03（F1 0.8326/0.8471/0.8451，中位 0.8451） |
| 一次人为劣化演练：改坏权重 → CI 应拦截 | ✅ 双轨 | 轨①自动化进 pytest（fc10c0e）；轨②以 T6 **真实**劣化案例替代人为演练（见 §2——真实 block→exit 1→恢复全链路，强于人工改权重） |
| 评测集 v1 冻结宣告 | ✅ | EVALUATION.md §2（E1×2 + E2 + E3 + 判定依据快照 + 开放项如实记录） |
| 报告生成（指标表/版本三元组/与上版差异） | ✅ | `eval-report`：真实库 14 条历史全呈现；差异**同版本优先**（跨版本明示"谨慎解读"） |
| CI 门禁上线 | ✅ 代码就绪 | `.github/workflows/ci.yml`（PR+push master pytest 全量 + 迁移预检；E1 仅 dispatch）；**首跑绿待 push**（workflow 须在远端才生效——本地已做 YAML 语法 + scratch 库命令序列演练） |
| 失败分诊流程文档化 | ✅ | EVALUATION.md §9（五类处置 + 本仓库具体化：Flaky 先查 extraction_failures 区分服务波动与真实回归） |
| 全量回归绿 + 六维自检 | ✅ | 443 绿；§3 |

## 2. 真实库劣化演练（C4 轨②——T6 意外获得的真实案例）

计划原设计为"人为改权重 → eval-gate exit 1 → 复原"。实际发生了**更真实的
版本**（DeepSeek 服务端波动，非人为）：

1. **劣化发生**：E1 跑分每轮 1-2 个 LLM 瞬时失败 → evidence_rate 0.96-0.98
   → 一票 block（eval_run #10-12）
2. **门禁拦截**：`eval-gate` 真实 exit 1——E2/E3 pass 在场仍被拦，
   "任一 block → 整体 block"规则在真实劣化下验证正确
3. **定位归因**：f1/recall 本身在 warn 区间，非阈值回归；查
   extraction_failures（1-2/轮）+ 轮 3 耗时翻倍（678s）→ 服务端波动
4. **恢复**：清 llm_cache 重跑（#13 缓存复现轮——缓存把 #12 的失败原样
   复现，指标逐位相同，佐证 C5 协议每轮清缓存的必要性）→ #14 failures=0
   → warn（F1=0.8628 与基线同水位）→ gate 恢复 exit 0

全链路（劣化 → 拦截 → 定位 → 恢复）恰好把 §9 分诊表的 Flaky 路径走了一遍。
**诚实声明**：人为改权重演练未单独执行——真实案例已覆盖同一证明目标
（gate 对 block 敏感且无误拦），且自动化轨①在 CI 内可重复验证。

## 3. 六维自检

### Product —— 真的解决问题吗？
评测体系回答的是"这次改动让什么变好了/变坏了"（§6 原文）——gate 让
Blocker 自动阻断合并、report 让 14 条历史可读、方差数据让"指标降了 1pp"
可以被正确解读为噪声。三者都是开发期真实需要的能力。

### Engineering —— 过度设计了吗？
克制点：gate 不重复判定单指标（import 评测器阈值，单一事实来源）、
report 复用 apply_gate 不二算、taxonomy 检查做成测试而非 CLI（无交互
价值）、CI 只跑测试不搬评测进 CI（数据在本地，如实记录为 §8 适配而非
硬凑原设计）。新增代码量：gate 88 行 + report 230 行 + workflow 99 行。

### AI —— LLM 被滥用了吗？
零新增 LLM 调用路径。E1 dispatch 任务手动触发 + 无 key skip 有提示
（key 泄露/费用/flaky 三风险不进 PR）。judge 分数延续"永不进门禁"红线
（T1 测试锚定）。

### Data —— 数字真实吗？
T6 方差演练诚实记录：三轮 verdict 均 block（非演练预期）、失败样本
拉低 recall 的量化归因、缓存复现轮 #13 逐位复制的机理。eval_run 14 条
历史全部真实入库（含演练轮），不删不改。

### Evaluation —— 结果可验证吗？诚实记录限制：
- 方差 PASS 建立在每轮清缓存上——不清缓存会得到零方差假信号（#13 实证）
- E1 verdict 对 LLM 可用性敏感（evidence_rate 一票 block）：warn 与 block
  之间隔着的是 DeepSeek 的稳定性而非系统质量——已写入分诊表处置
- 零漂移测试的 fixture 市场 ≠ 真实 201 岗市场（速度与覆盖的折衷，
  如实声明）
- CI 首跑绿验收**未完成**（依赖 push，本地已尽最大验证）——这是本阶段
  唯一开放验收项

### Resume —— 简历价值？
可讲：分层评测门禁设计（PR 快检 vs 全量基线的工程化裁决）、真实劣化
案例（服务波动 vs 真实回归的分诊）、方差协议（清缓存防假信号——有
实证）、报告的诚实性设计（同版本优先的 diff 基线）。

## 4. 遗留与移交

| 项 | 状态 | 处置 |
|---|---|---|
| CI 首跑绿验收 | ⏳ 待 push | workflow 须在远端生效；push 后盯首跑，若红仅修 yml 不动测试（计划风险表） |
| E1 dispatch 验收 | ⏳ 待 push + secret | 需在 GitHub 配 `LLM_API_KEY` 后手动 dispatch 一次 |
| E3 标注双人复核 | ⏳ 用户 + 同学 | 不阻塞；e3-v1 冻结不受影响（v2 扩集时复核） |
| E1 verdict 对 LLM 可用性敏感 | 已记录 | 不改冻结规则（Phase 9 纪律）；若未来频繁误拦，复议 evidence_rate 一票 block 的粒度（如失败样本重试一次）——记 DECISION_LOG 待议 |

## 5. 下一步（Phase 10 Dashboard）

按 ROADMAP：六视图 + 数字可点击溯源（evidence_ref）。Phase 9 的
eval-report Markdown 结构可为 Dashboard 的"评测页"复用。
