# Phase 4 Review —— Market Intelligence 验收与六维自检

> 2026-09-02 ｜ 执行计划：`docs/plans/2026-09-02-phase4-market-intelligence.md` ｜ 代码：200 测试全绿 ｜ 零新迁移 / 零新依赖

## 0. 交付物清单

| 交付物 | 位置 | 说明 |
|---|---|---|
| 切片频率统计 | `src/skillgap/stats.py` | 整体 + 4 维切片（岗位类/城市/薪资段/时间窗），API §2.11 服务层结构 |
| 快照生成 | `stats.py::create_snapshot` | append-only，method_version=s11-v1，N<30 拒写表 |
| 技能溯源 | `stats.py::skill_evidence` | API §2.12 底账，consent 口径与统计一致 |
| 交叉对照 | `stats.py::crosscheck_baseline` | Kendall tau-a + 14 技能逐条 diff（vs MARKET_RESEARCH §2.1） |
| CLI | `skillgap stats / snapshot-create / skill-evidence / market-crosscheck` | 4 命令，切片参数齐全 |
| 口径文档 | `docs/STATS_METHOD.md` | 统计口径文档化（ROADMAP Phase 4 产出项） |
| 首跑记录 | `docs/plans/phase4_first_run_results.md` | snapshot#1 / tau=0.1538 / 守门真实验证 |

Commits（仅本地）：ff8aa90（切片统计）→ 8c72f71（快照）→ 3941c37（溯源）→ ef13489（交叉对照）→ 97e2d64（CLI）→ 52df418（口径文档）。

## 1. 验收核验表（ROADMAP Phase 4 逐条）

| 验收项 | 结果 | 证据 |
|---|---|---|
| 每个百分比可追溯到 JD 列表 | ✅ | `skill-evidence --skill RAG` → 27 条 jd_refs，evidence_text 逐条回原文（首跑记录 §2） |
| 统计口径文档化 | ✅ | `docs/STATS_METHOD.md`（过滤口径/切片语义/frequency 公式/守门分级/版本纪律/对照方法/底账口径，7 节）；METHOD_VERSION=s11-v1 入每份输出 |
| 与 MARKET_RESEARCH §2.1 交叉对照，差异写入报告 | ✅ | tau=0.1538 + 14 技能逐条 diff（首跑记录 §3）：方向接近 RAG -0.06 / PromptEng -0.11 / LangGraph -0.11 / MCP +0.10；最大偏差 LangChain -0.64（参考表生态偏置）、Java +0.43（自采数据大厂后端岗占比高）——差异已逐条写入报告，无聚合遮蔽 |
| （ROADMAP 产出项）切片统计：岗位类/城市/薪资段 | ✅ | 4 维切片测试覆盖（test_stats.py 12 项统计测试）；agent_dev 真实切片 N=20 < 30 被守门拒绝 |
| （预留）时间切片查询 | ✅ | window 切片已实现（BETWEEN 含端点），趋势对比留待数据积累（MVP Should Have 触发条件：N≥100 且跨度 ≥30 天） |

## 2. 首跑关键数字（2026-09-02，N=50，全部 public_job_page / tier_a）

- **snapshot#1**：50 岗位，confidence=medium，窗口 2026-08-31～09-01，57 技能入表
- **Top 5**：Python 0.76 ｜ Java 0.58 ｜ RAG 0.54 ｜ Go 0.40 ｜ Prompt Engineering 0.34
- **tau=0.1538**：与 §2.1 参考表仅弱一致——方向对照成立但印证参考表只能作假设生成器；自有数据才是可复现、可追溯的口径
- **守门真实验证**：agent_dev 切片 N=20 → `insufficient_sample`，未输出任何频率数字

## 3. 六维自检

### Product —— 真的解决问题吗？
M8（分市场技能频率统计 + 样本量 + 来源分布 + 溯源）服务层闭环。用户视角的三个承诺全部兑现：每个百分比附 N/窗口/来源分布/置信度；N<30 明示样本不足；两市场永不混算（STATS_FILTER + market 参数 + 既有市场分离测试）。缺口：尚无 API 层（Phase 11 前 CLI 即产品面）与趋势对比（数据量未达触发条件，属预期后置）。

### Engineering —— 过度设计了吗？
零新表（market_snapshot 为 Phase 2 已建）、零新依赖、零迁移。核心是 3 个函数 + 1 个纯函数（kendall_tau），复用冻结的 STATS_FILTER 与 _slice_where，SQL 参数化无拼接注入面。两个口径决策（city 子串匹配、薪资区间重叠）均已文档化并写进测试，不是隐式行为。快照 append-only 而非 upsert——历史可追溯优先于省空间，符合评测资产定位。

### AI —— LLM 被滥用了吗？
零 LLM。守卫测试 `test_stats_module_zero_llm_dependency` 锁定 stats.py 源码不得含 llm/extract 引用（CI 静态检查的先行落地）。tau/diff/frequency 全部为 SQL 与纯函数。

### Data —— 数字真实吗？
数字 100% 来自自有数据集（50 条，来源分布透明：company_career_page/tier_a/share=1.0）。溯源底账与统计同口径（未授权贡献永不进任何输出）。交叉对照的诚实边界：tau=0.1538 如实报告弱一致，不粉饰；参考表定位（非官方 23 JD 小样本）在报告与口径文档双重声明。批次 1 抽查发现并修复的薪资误判 bug（30a7370）保证了首跑快照的薪资切片可信。

### Evaluation —— 结果可验证吗？
同版本重跑零漂移：纯 SQL + 确定性函数，无 LLM 方差。快照进 DB 历史（append-only + method_version），评测口径（tau-a 计算方式）文档化且 REFERENCE 表有防漏抄测试（14 条键集校验）。守门行为在真实数据上验证（agent_dev N=20 拒绝），不是只存在于单测。

### Resume —— 简历价值？
"所有频率数字都是 SQL 算的、每个百分比能点开看支撑 JD 列表、样本不足时系统宁可不出数——三层分离 + 数据诚实设计。" 面试可展开：为什么溯源底账不做样本量守门（事实列举 vs 统计推断）；为什么用 tau-a 而不是直接对比数值；为什么快照 append-only。

## 4. 遗留与下一步

1. **批次 2-4 收集**（50 → 200-300 条）：N=50 仅 medium 置信度；城市/薪资切片多数仍 <30。数据积累后快照自动升级置信度，趋势对比解锁
2. **E1 真实基线**（等 LLM_API_KEY）：仍是 Phase 3 验收唯一遗留
3. **Adzuna 首批**：global 市场快照通道已就绪（stats --market global），等拉取后即可产出首份 global 对照
4. **Phase 5 Candidate Profile**：下一开发阶段（Plan → Implement → Test → Review）

## 5. 结论

**PASS。** ROADMAP Phase 4 全部验收项达成，六维自检无红线问题。首跑产出项目第一份可复现、可溯源的中国市场技能频率快照（snapshot#1），交叉对照与守门行为均在真实数据上验证。
