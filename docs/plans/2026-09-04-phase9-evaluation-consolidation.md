# Phase 9：Evaluation 汇总（系统级）实施计划

> **Goal**：三层评测体系化收口——评测集 v1 冻结宣告、评测报告生成（版本三元组 + 与上版差异）、CI 门禁（GitHub Actions）、失败分诊文档化、EVALUATION.md（README 级）；一次人为劣化演练证明"评测不是装饰"。
> **Architecture**：增量层——`eval/gate.py`（门禁纯函数：读 eval_run 历史 × 阈值表 → 汇总 verdict）+ `eval/report.py`（Markdown 报告：eval_run 历史时间序列 + 差异）；CI 走 GitHub Actions（pgvector 服务容器）。**不动三评测器本体**（E1/E2/E3 已冻结口径，本阶段只消费其 eval_run 产出）。
> **Tech Stack**：既有栈零新依赖；CI 新增 GitHub Actions（仓库首个 workflow）。

## Context

Phase 8 已收口：E1（eval-v1/v2，F1=0.9043/0.8669）+ E2（e2-v1，ρ=0.8433）+ E3（e3-v1，nDCG@5=0.6497）+ judge（mean=5.0，eval_run #9）全部入库。阈值表已冻结在各评测器内（E1 `THRESHOLDS`、E2 `E2_THRESHOLDS`、E3 起步线）——本阶段做的是把这些**散落的 verdict 变成一道系统级门禁**。

现状缺口（对照 ROADMAP Phase 9 产出）：
1. 无 CI（`.github/` 不存在）——394 测试只在本地跑
2. 无报告生成——eval_run 有 9 条历史但只能手写 SQL 看
3. 无系统级门禁——单评测器各有 verdict，但没有"任一 block 即整体 block"的汇总出口
4. 劣化演练未做过——"CI 能不能真拦住坏改动"从未验证
5. EVALUATION.md 不存在——评测资产没有 README 级呈现

## 口径裁决（先落 DECISION_LOG D-2026-09-04-17，再动代码）

| # | 冲突/空白 | 裁决 |
|---|---|---|
| C1 | EVALUATION_PLAN §8 要求"main: E1-E3 全量评测 + 结果入库"，但真实市场数据（201 china 岗）与 LLM key 都在本地，CI 无法触达本地库；且入库 JD 原文违反数据治理（仓库不分发数据） | **CI 分层**：PR = 全量 pytest（评测器逻辑已由 fixture 测试覆盖——E2/E3 全链路、E1 无 key 路径、劣化演练测试）+ taxonomy 一致性检查；**全量基线评测留在本地**（eval_run 即 source of truth），gate/report 命令离线读库工作且被单测锚定。如实记录为 §8 的工程化适配（原则不变：阈值 Block 即失败） |
| C2 | E1 在 CI 跑需要真实 LLM（key 泄露风险 + 费用 + flaky） | E1 CI 任务**仅 workflow_dispatch 手动触发**（secrets 注入），PR/push 不跑；本地 variance 演练同理手动。E2/E3 确定性零 LLM，理论可进 CI——但因 C1（无真实市场数据）同样归入 dispatch 可选项，默认 PR 只跑测试 |
| C3 | gate 的退出码语义（E3 judge "Warn 不参与 verdict" 已有先例） | `eval-gate`：block → exit 1（阻断合并）；warn → exit 0 + stderr 明示（Warn 级不阻断，与 judge 同纪律）；pass → exit 0。**judge 分数永不进门禁**（rubric-v1 是参考信号）。缺评测类型基线（如 E3 无任何 run）→ warn 不 block（首次跑分前的正常态），stderr 提示 |
| C4 | 劣化演练怎么"CI 应拦截"才可复现 | **双轨**：①自动化测试（进 pytest，即进 CI）——`monkeypatch.setitem(scoring.WEIGHTS, 'coverage', 0.0)` 改坏权重 → run_e2（fixture 市场）→ ρ 崩 → gate 断言 block——这就是"PR 带劣化会被拦"的可重复证明；②真实库手动演练一次（改权重 → eval-gate exit 1 → 复原）记入 PHASE_9_REVIEW。不改任何生产代码 |
| C5 | E1 方差 ≤3% 验收：llm_cache 会让 3 连跑零方差（假信号） | 演练每轮 `TRUNCATE llm_cache` 后跑 `eval-e1`，共 3 轮，取 F1 极差/中位数；结果如实记 EVALUATION.md（不达标就记录实际值 + 归因，不粉饰） |

## 冻结的设计决策

| # | 决策 |
|---|---|
| D1 | `eval/gate.py`：`apply_gate(runs: Mapping[str, Mapping]) -> dict` 纯函数——输入 `{eval_type: 最新 run(metrics, verdict)}`，输出 `{overall, per_type, blocking}`。阈值**不重复定义**：直接 import E1/E2/E3 模块的阈值表（单一事实来源）；gate 只做"多类型汇总 + 退出码映射"，不重新判定单指标（那是评测器的职责） |
| D2 | gate 取数规则：每个 eval_type 取**最新一条** eval_run（按 id DESC）；支持 `--run-id N` 显式指定（报告/演练用）。`eval-gate` CLI 输出 JSON（per_type verdict + overall）+ 退出码（C3） |
| D3 | `eval/report.py`：`generate_report(conn, out_path) -> str`——Markdown，结构=①版本三元组表（每类型最新 run 的 prompt/dataset/scoring version + sample N）②指标表（关键指标 + 与上一条 run 的差异箭头）③eval_run 时间序列（全部历史一行一条）④诚实边界脚注（§9 的 N 与版本要求）。CLI `eval-report [--out P]` 默认 stdout |
| D4 | 零漂移验收（ROADMAP："同版本重跑确定性指标零漂移"）：自动化测试——`run_e2`/`run_e3` 在同一 fixture 市场上连跑两次，断言两次 metrics dict **完全相等**（E1 排除：LLM 非确定性，由 C5 方差演练覆盖） |
| D5 | taxonomy 一致性检查（EVALUATION_PLAN §6"词表与评测集一致性由 CI 检查"）：纯函数检查 e1/e2/e3 三份标注集里出现的技能名 ⊆ 词表 canonical_name（文件级，读 JSON + taxonomy CSV）；实现为测试（进 pytest 即进 CI），不做成 CLI（无交互价值） |
| D6 | CI workflow（`.github/workflows/ci.yml`）：PR + push main 双触发；`pgvector/pgvector:pg16` 服务容器（POSTGRES_USER/PASSWORD=skillgap 对齐 conftest 的 ADMIN_URL 硬编码，POSTGRES_DB=postgres 供 ensure_database 建 skillgap_test）；步骤=checkout → setup-python 3.11（pip cache）→ `pip install -e ".[dev]"` → `db-upgrade`（TEST_DATABASE_URL）→ pytest 全量；E1 dispatch 任务（`workflow_dispatch`）gated on `secrets.LLM_API_KEY`，缺席时 skip 并打印原因 |
| D7 | 评测集 v1 冻结宣告（本阶段产出）：E1 `eval-v1`/`eval-v2`（53 JD）+ E2 `e2-v1`（22 对）+ E3 `e3-v1`（5 画像）+ 判定依据快照（E2/E3 基线锚定 market snapshot#4 china N=201）；冻结=新用例进 v2 不改 v1（既有纪律，EVALUATION.md 正式宣告）。**开放项如实记录**：E3 标注双人复核（user + 同学抽标）仍未完成，不阻塞本阶段 |
| D8 | 失败分诊流程文档化：EVALUATION.md 内嵌 §7 分诊表（Blocker/可接受回归/Flaky/数据问题/覆盖缺口五类处置）+ 本仓库的具体化（Flaky=DeepSeek 重试耗尽 → LLMError → 评测 rc=1 直接失败不重试；数据问题=修标注须 dataset_version+1 全量重跑） |

## 文件结构

```
src/skillgap/eval/gate.py          # apply_gate 纯函数 + 取数（最新 per type）
src/skillgap/eval/report.py        # Markdown 报告生成
src/skillgap/cli.py                # +eval-gate / +eval-report
.github/workflows/ci.yml           # 仓库首个 CI（PR/main + E1 dispatch）
docs/EVALUATION.md                  # README 级评测文档（三层地图/冻结版本/阈值/基线/方差/演练/分诊/诚实边界）
tests/test_eval_gate.py            # 汇总逻辑 + 退出码 + 缺类型 + judge 不进门禁
tests/test_eval_report.py          # 报告结构 + 差异计算 + 版本三元组
tests/test_eval_determinism.py    # 零漂移双跑 + taxonomy 一致性 + 劣化演练自动化
```

## 任务分解（TDD）

| # | 任务 | 交付 | 验收 |
|---|---|---|---|
| T1 | gate 纯函数 + CLI | `gate.py` + `eval-gate` + `test_eval_gate.py`（≥8 项：全 pass / 单类型 block → 整体 block / warn 不阻断 / 缺类型提示 / judge 分数被忽略 / --run-id） | pytest 绿；`eval-gate` 对当前真实库跑出 overall=pass（E1 warn F1=0.8669 <0.85 但 E2/E3 pass——预期 overall=warn，exit 0，正好验证真实场景） |
| T2 | 劣化演练（自动化） | `test_eval_determinism.py` 内 monkeypatch WEIGHTS → run_e2 → gate block 断言 | 测试证明"权重改坏 → ρ 崩 → gate exit 1"；含反向断言（不改权重时同路径 pass，防测试自欺） |
| T3 | 报告生成 | `report.py` + `eval-report` + `test_eval_report.py`（≥6 项） | 对真实库生成报告含 9 条历史 + E2/E3 基线差异行；Markdown 结构测试锚定 |
| T4 | 零漂移 + taxonomy 一致性 | `test_eval_determinism.py` 其余用例 | run_e2/run_e3 双跑 metrics dict 相等；三份标注集技能 ⊆ 词表 |
| T5 | CI workflow | `ci.yml` | 本地 act 不验（无 Docker 动作约束），push 后 GitHub 首跑绿（PostgreSQL 服务 + 410 测试）；E1 dispatch 任务在无 secret 时 skip 有提示 |
| T6 | E1 方差演练（本地真实） | 3 轮 eval-e1（每轮清 llm_cache） | F1 极差 ≤3% 或如实记录实际值；结果写 EVALUATION.md |
| T7 | EVALUATION.md + 收口 | 文档 + PHASE_9_REVIEW + 文档同步 + 全量回归 | 六维自检；ROADMAP/HANDOVER 状态更新；D-17 落 DECISION_LOG |

## 风险与对策

| 风险 | 对策 |
|---|---|
| CI 服务容器 pgvector 权限/健康检查配置错误导致首跑红 | conftest 的 ADMIN_URL 硬编码 `skillgap:skillgap@localhost:5432/postgres`——服务容器 env 完全对齐该值；health-options `pg_isready -U skillgap` |
| Windows 本地 `act` 无法预演 workflow | 接受：push 后看首跑；若红仅允许修 yml（不动测试迁就 CI） |
| 劣化演练测试改权重后忘记复原污染其他测试 | monkeypatch 作用域天然回滚（pytest fixture）；测试内断言复原后 SCORING_VERSION 不变 |
| E1 方差超 3%（DeepSeek 非严格温度 0） | 如实记录实际极差 + 归因（temperature=0 非确定性承诺）；不粉饰不达标 |
| eval_run 历史混入测试脏数据（gate 误读） | gate 只读**主库**；测试全部走 clean_db fixture 的 test 库（既有纪律，无新风险） |

## 验收清单（对照 ROADMAP Phase 9）

- [ ] 同版本重跑确定性指标零漂移（T4 自动化）
- [ ] LLM 指标方差 ≤3%（T6 真实演练，或如实记录）
- [ ] 一次人为劣化演练：改坏评分权重 → CI 应拦截（T2 自动化 + 真实库手动一次）
- [ ] 评测集 v1 冻结宣告（EVALUATION.md）
- [ ] 报告生成含指标表/版本三元组/与上版差异（T3）
- [ ] CI 门禁上线（T5：PR 快检 + E1 dispatch）
- [ ] 失败分诊流程文档化（EVALUATION.md §分诊）
- [ ] 全量回归绿 + PHASE_9_REVIEW 六维自检
