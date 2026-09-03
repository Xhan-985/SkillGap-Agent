# Phase 6 Review —— Skill Gap 验收与六维自检

> 2026-09-03 ｜ 执行计划：`docs/plans/2026-09-03-phase6-skill-gap.md` ｜ 代码：288 测试全绿（243 存量 + 45 新增）｜ 零新迁移 / 零新依赖 / 零 LLM

## 0. 交付物清单

| 交付物 | 位置 | 说明 |
|---|---|---|
| gapcalc 纯函数 | `src/skillgap/gap/gapcalc.py` | gap-v1：required_level 映射（含 NULL 缺省/nice 封顶）/ gap clamp / classify 判定，零 skillgap 依赖（守卫测试锁定） |
| 服务层 | `src/skillgap/gap/service.py` | get_gaps 双模式：单岗（job_id）/ 类目聚合（category + market + min_freq）；transferable note 溯源 relation.note；快照引用 |
| CLI | `skillgap gap-get` | 1 命令双模式；404 → rc=1、互斥参数 → rc=2 |
| 口径裁决 | `docs/DECISION_LOG.md` D-2026-09-03-13 | C1（confidence 不进 gap——ROADMAP 与 DATA_MODEL 冲突裁决）+ C2（类目聚合规则冻结）+ D1-D8 |
| 测试 | 3 个文件 +45 项 | gap_calc 22 项（单调性/边界/守卫）+ gap_service 20 项（真实 PG）+ CLI 4 项 |
| 文档同步 | API.md §2.9 / DATA_MODEL §4.2 / ROADMAP / HANDOVER | 聚合规则、NULL 缺省、响应结构（mode/via/gap_version）落档 |

## 1. 验收核验表（MVP M7 / ROADMAP Phase 6 逐条）

| 验收项 | 结果 | 证据 |
|---|---|---|
| 能力提升 → 缺口单调收窄（纯函数单测） | ✅ | test_gap_calc.py `test_gap_monotonic_narrowing`：required=4，actual 0→5，gap [4,3,2,1,0,0] 单调非增 |
| 完全无关岗位边界用例 | ✅ | `test_unrelated_job_all_genuine`：Docker/Git 零关联 → 全 genuine、actual=0 全额缺口 |
| 完全达标岗位边界用例 | ✅ | `test_fully_qualified_job_empty_gaps`：gaps=[] |
| （产出项）Gap 计算 pure function | ✅ | gapcalc.py 零依赖 + 守卫测试（无 import skillgap） |
| （产出项）transferable/genuine 区分 | ✅ | classify 单测 6 项（阈值 0.5 含边界 0.49/0.50、parent 链、自身证据）+ 服务层 Java↔Python 种子关系集成测试 |
| （产出项）最大缺口清单（ROI 排序原料） | ✅ | 每行带 demand{frequency,sample_size} + cost；排序 gap 降序→frequency 降序；Phase 8 roi-v1 消费 |
| （API §2.9）单岗 / 类目聚合双模式 | ✅ | 类目规则：频次 ≥0.20 入清单、required 取 must 映射最大值、快照引用（服务层 7 项测试） |

## 2. 设计决策（DECISION_LOG D-2026-09-03-13）

- **C1 confidence 不进 gap**：ROADMAP Phase 6 原文"含 confidence 折减"与 DATA_MODEL §4.4（H1 修复）冲突——按 DATA_MODEL 裁决（gap=纯星级差，conf_factor 属 Phase 7 match）。ROADMAP 措辞已修正，避免两套口径
- **C2 类目聚合规则**：API §2.9 原文只写"用市场聚合要求"无规则——冻结为：频次 ≥ min_freq(0.20) 入清单（参数可覆盖）；required = must_have 行映射最大值（无则 2）；demand 带 category_sample_size + 最新快照引用
- **D1 intensity NULL 缺省**：must_have → 3（熟悉中性档）/ nice_to_have → 2——真实数据存在 NULL intensity 行（LLM 抽取不总产出程度词）
- **transferable 的 via/note 语义**：via=证据技能（自身优先——"已有证据但等级不足需深化"；否则关联技能，note 取 skill_relations_v1.csv 种子 note，可被"死亡追问"到原始关系表）

## 3. 六维自检

### Product —— 真的解决问题吗？
M7 闭环：`gap-get --candidate-id N --category c` 一条命令输出"该补什么、为什么、缺口多大、市场多需要"。真实 e2e（§4）：62 岗类目聚合 → AI Coding gap4 genuine / Prompt Engineering freq 0.48 gap3 / Python 精通要求 vs level3 → "需深化"而非"零基础"。每个数字可溯源：星级差可手算、frequency 可回查快照、transferable note 可回查关系表。

### Engineering —— 过度设计了吗？
零新表（skill_relation/parent_skill_id Phase 2 已建）、零迁移、零新依赖、零 LLM。gapcalc 纯函数 68 行，服务层复用 stats 的 STATS_FILTER 口径（同源同口径）；required_level 映射只在 gapcalc 一处（类目聚合也走它，单一事实来源）。类目聚合在 Python 分组而非 SQL 聚合——N≈200 量级下可读性优先，且避免在 SQL 里硬编码程度词映射表两处维护。

### AI —— LLM 被滥用了吗？
全链路零 LLM（Phase 6 无任何 LLM 调用——gap 是 SQL+纯函数）。守卫测试锁定 gapcalc.py 无 skillgap import；服务层数值全部来自 DB 查询与 gapcalc。这也是 Phase 7 match 评分器的前置纪律演练。

### Data —— 数字真实吗？
demand 与 stats S11 同口径（STATS_FILTER 复用，未复制粘贴第二份过滤逻辑）；frequency 可与 snapshot#4 对照（e2e 中 AI Coding 0.2097 与快照一致）；类目 sample_size 明示（62≠201，避免拿类目数字冒充全市场）；无快照时 snapshot=None 不臆造。

### Evaluation —— 结果可验证吗？
gap-v1 纯函数零漂移；单调性/边界用例直接锚定 MVP 验收原文。**已知限制（诚实记录）**：min_freq=0.20 与证据线 0.5 均为 heuristic 首值，无标注集背书（E2 属 Phase 7，届时用 matching 标注校准）；transferable 判定依赖 skill_relations_v1.csv 仅 6 条种子——覆盖面薄（Java↔Python 等），词表 87 技能中绝大多数缺口技能无关系数据可判，只能落 genuine（保守方向：宁可 genuine 不虚报 transferable）。

### Resume —— 简历价值？
"Gap 报告不是分数堆，是可解释的决策依据。" 面试可展开：为什么 confidence 不进 gap（星级差是事实，置信度是匹配层的折扣——两层分离）；为什么 transferable 判定走词表关系而非 LLM 判断（确定性可回归）；为什么类目聚合取 must 最大值（招人方按最高要求对标）。

## 4. 真实 e2e 验证（2026-09-03，真实 LLM + N=201 真实数据）

用户真实简历（data/resume_sample.txt，Phase 5 样例）→ `resume-analyze`（candidate 3：Java conf 1.0 L3 / Python conf 1.0 L3 等）→ `gap-get --category ai_application_dev`（真实库 62 岗、snapshot#4 N=201 high 引用）：

- Top genuine 缺口：AI Coding（gap 4，freq 0.21）/ Prompt Engineering（gap 3，freq 0.48）/ 多模态（gap 3，freq 0.24）/ C++（gap 3）
- Transferable：Python required 5（类目内 must 精通）vs L3 → gap 2"自身已有证据但等级不足（需深化）"；Java required 4 vs L3 → gap 1 同类
- 排序与 demand 核验通过；exit code 0

## 5. 遗留与下一步

- **Phase 7 Job Matching**（下一步）：确定性加权评分器（scoring_version 版本化）+ E2 标注集（20-30 对，Spearman/MAE/Jaccard）——E2 同时校准本阶段 heuristic（min_freq/0.5 证据线/权重表）
- skill_relations 词表覆盖面扩充（当前 6 条 transferable_to 种子）——随 Phase 7 E2 需要再扩，不提前铺量
- Adzuna 首批拉取仍在队列（HANDOVER §9-5）
