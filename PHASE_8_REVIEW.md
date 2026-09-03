# Phase 8 Review —— Recommendation 验收与六维自检

> 2026-09-03/04 ｜ 执行计划：`docs/plans/2026-09-03-phase8-recommendation.md` ｜ 代码：394 测试全绿（377 存量 + 17 新增）｜ 零迁移 ｜ 新依赖 langgraph 0.3.34（首个，ADR-006 冻结时机）｜ E3 基线 **pass**

## 0. 交付物清单

| 交付物 | 位置 | 说明 |
|---|---|---|
| ROI 纯函数 | `src/skillgap/recommend/roi.py` | roi-v1：potential_gain = Demand×Gap÷Cost（low=1/mid=2/high=3）+ 频次过滤（<0.20）/ 同分按频次 / Top-K / rationale 模板（数字 100% 源自 item）；零 skillgap import + 零 LLM（守卫测试锁定） |
| 服务层 | `src/skillgap/recommend/service.py` | recommend：market 全类目聚合（C4，复用 D-2026-09-03-13 规则）+ snapshot demand 溯源 + 模板匹配（D4）+ recommendation 落库；ADR-008 守门（<30 岗拒推） |
| 模板库 | `data/project_templates.json` | 12 条人工策划项目模板（source 必填——策划依据合规审计） |
| Career Planner Agent | `src/skillgap/recommend/agent.py` | LangGraph 图 load（确定性）→generate（叙事）→verify（数字程序校验）→revise 一次→降级模板；TypedDict reducer state |
| E3 评测器 | `src/skillgap/eval/e3.py` | nDCG@5（增益 2^rel−1）/Precision@5/HitRate@3/coverage 纯函数 + seed_eval3 幂等入库 + run_e3（画像物化复用 e2 + eval_run 留痕）；指标零 LLM |
| E3 标注集/报告 | `data/eval/e3_seed_v1.json` / `e3_report_v1.json` | 复用 E2 五画像 × 相关性三档标注；基线报告含已知偏差分析 |
| CLI | `recommend` / `agent-plan` / `eval-e3` | 零模型直通 / LangGraph 叙事（需 key）/ 指标零 LLM 无 key 可跑（--dataset/--seed-only） |
| 测试 | 5 个文件 +17 项 | roi 15（任务 1）+ service 12（任务 2）+ CLI 3（任务 3）+ agent 8（任务 4）+ E3 指标/runner 17（任务 5，含修复 hit_rate 数据对齐错误与旧 coverage 实现笔误） |

## 1. 验收核验表（MVP M9 / ROADMAP Phase 8 / EVALUATION_PLAN §4）

| 验收项 | 结果 | 证据 |
|---|---|---|
| E3 nDCG@5 ≥ 0.5 起步 | ✅ | **0.6497**（eval_run #8 留痕，verdict=pass）；hit_rate@3=1.0 / coverage=0.95 / precision@5=0.60 |
| 数值正确性 100%（纯函数） | ✅ | roi.py 守卫测试（零 import/零 LLM）+ 公式逐项单测 + E3 指标手算锚定（含 2^rel−1 增益公式） |
| 解释引用一致性（程序比对） | ✅ | check_consistency：LLM 叙事数字 ⊄ 规则产出派生集即拦截；真实 e2e 两次拦截（"20 个评测用例"中的 20 无来源）→ revise → 降级模板，数字零污染（trace 留痕） |
| Agent 回放（同输入同 trace 确定性部分） | ✅ | test_recommend_agent.py：Fake LLM 下 load/verify 节点输出确定；trace 结构化留档（step/ok/bad_nums） |
| LLM 不参与指标计算 | ✅ | eval-e3 无 key 全链路可跑（CLI 测试锚定）；gateway 参数仅预留给叙事/judge 层 |
| rationale 无公式外数字 | ✅ | 模板测试 + D3 派生集口径 |
| ADR-008 守门（<30 岗不臆造） | ✅ | INSUFFICIENT_MARKET_DATA 拒推（service + CLI 双测试） |

## 2. E3 基线数字（2026-09-04，china N=201 × 五画像，eval_run #8）

```json
{"ndcg@5": 0.6497, "precision@5": 0.60, "hit_rate@3": 1.0,
 "coverage": 0.95, "verdict": "pass",
 "per_case": [0.5792, 0.8811, 0.4848, 0.6841, 0.619]}
```

逐画像：P2 全栈均衡 0.88 最高；P3 新手 0.48 最低；P5 裸声明 0.62（conf 0.3 不进排序，纯星级差口径下无异常——对抗用例未发现裸声明投机空间）。

## 3. 六维自检

### Product —— 真的解决问题吗？
`recommend --candidate-id 3` 一条命令输出"学什么最值"（Top-10 ROI 排序 + 每项频次/缺口/成本/优先分 + 12 模板项目匹配）；`agent-plan` 输出个性化 150 字叙事。真实用户（candidate 3，本人简历画像）：Python（transferable，1.31）> PE（1.21）> AI Coding（1.09）——与"RAG 强、工程弱"的画像一致。

### Engineering —— 过度设计了吗？
零迁移（recommendation 表 Phase 2 已建）；模板匹配纯集合运算；LangGraph 只包 4 节点单图（load→generate→verify→END/revise/降级），复杂度与"需要条件路由 + 校验回退"的问题规模匹配——ADR-006 复议结论：**引入成立但边界严格**（解释个性化是规则覆盖不了的场景；但数值路径零 LLM 权限，Agent 是旁路层，撤除不影响核心——Reversibility 验证）。反例自觉：如果 v1 就上 Agent，白盒计算变黑盒链，E3 无法归因。

### AI —— LLM 被滥用了吗？
数值路径 100% 规则（守卫测试）；LLM 仅叙事层（verify 拦截 + revise 一次 + 降级模板永不失一致性）。真实 e2e 证据：DeepSeek 生成"20 个评测用例"（无来源数字）→ 程序拦截 → revise 仍带 20 → **降级模板**（fallback=true，trace 六步完整留档）——红线在真实流量下工作。

### Data —— 数字真实吗？
demand 全部来自 snapshot#4（china, N=201, high）+ 实时 SQL 聚合双通道；模板库 12 条 source 必填；E3 标注锚定市场真实频次（独立人工判断，非系统输出回抄）。

### Evaluation —— 结果可验证吗？诚实记录限制：
1. **nDCG@5=0.6497 未达 0.7 pass 线**（达 0.5 起步线）：主因是两个系统性偏差（见 e3_report_v1.json analysis）——①"Python 补到精通"偏差：市场 must_have 最高档为精通（required=5），level 3 画像一律 gap=2 且 gain≈1.31 全场第一，但标注者视为"已具备"（rel=0），压低 P1/P3/P5；②新手画像（P3 最低 0.48）下低成本工程效率类（AI Coding）排在中成本核心类（RAG）前，与"先核心后效率"标注观冲突。均为 v2 校准候选（required 分位数化 / 预算感知加权），留 DECISION_LOG 痕迹，不回改 e3-v1 冻结标注
2. **标注薄样本**：5 画像 × 1 条排序（D8 已知）；claude 初标 + user 复核待完成，同学抽标 ≥1 画像待办——v2 扩 8-10 画像复验
3. ~~**judge（rubric-v1）与 RAG 引用层未做**~~ → **2026-09-04 补做完成**（用户要求提前处理）：judge rubric-v1 已落地（真实基线 mean=5.0 / 5 条全覆盖，eval_run #9；满分符合预期——模板输出数字 100% 源自 item 无幻觉空间，rubric 区分度待 v2 评 Agent 叙事时体现；Warn 级不参与 verdict 的红线由测试锚定）；RAG 引用层代码完成（migration 004 + rag-index/rag-search CLI + retrieval 服务），等用户注册 embedding API（硅基流动 bge-m3）后 `rag-index` 回填即可用

### Resume —— 简历价值？
可展开叙事：①"我先证明规则够用，才在需要推理的环节引入 LangGraph"——roi-v1 纯函数先行独立验收（任务 1-3 零 Agent），Agent 只做规则覆盖不了的个性化解释；②"Agent 拿不到改数字的权限"——verify 节点程序比对 + 真实 e2e 拦截降级案例（trace 可展示）；③ nDCG@5 增益公式（2^rel−1）与排序质量评测的工程落地。

## 4. 真实 e2e（2026-09-04）

- **规则推荐**（candidate 3，零 LLM）：Top-3 = Python 1.31（transferable）/ PE 1.21 / AI Coding 1.09；项目建议提示词评测套件（7 天覆盖 PE+Python）
- **Agent 叙事**（真实 DeepSeek）：trace = load→generate→verify(bad_nums=["20"])→revise→verify(仍 "20")→end(fallback)；LLM 两次生成"20 个评测用例"均被拦截 → 降级模板输出（数字 100% 规则产出）——M9 红线在真实 LLM 流量下的完整工作证据

## 5. 下一步（Phase 9）

评测汇总（系统级）：E1+E2+E3 集成 CI 门禁 + 评测报告生成 + 人为劣化演练。本阶段已备好：E3 runner 复用 E1/E2 基建（evaluation_sample/eval_run/backfill 模式），三评测器的 eval_run 历史连续可查（#2 E1 / #1-#7 E2 / #8 E3）。
