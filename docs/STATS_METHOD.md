# STATS_METHOD —— 市场统计口径文档

> SkillGap Agent ｜ Phase 4 交付物（ROADMAP Phase 4 产出项"统计口径文档化"）
> 权威引用：DATA_PIPELINE S11 ｜ ADR-008（样本量守门）｜ API.md §2.11/§2.12 ｜ MARKET_RESEARCH.md §2.1
> 实现位置：`src/skillgap/stats.py`（零 LLM 依赖，CI 静态检查目标，守卫测试锁定）
> 当前口径版本：**method_version = s11-v1**（2026-09-02 冻结）

---

## 1. 统计过滤口径（STATS_FILTER）

所有统计与溯源查询共用的基础 WHERE 条件（原文，冻结）：

```sql
j.status = 'active' AND (j.source_type <> 'user_submitted' OR j.consent_status = 'market_analysis')
```

解释：

- **`status = 'active'`**：只统计当前有效岗位。quarantine（质检隔离）、rejected（质检拒绝）等状态的记录一律不进统计。
- **未授权贡献排除**：`user_submitted`（用户贡献）的岗位，仅当贡献者明确授权用于市场分析（`consent_status = 'market_analysis'`）时才纳入；其余同意状态（如 none / 未授权）**永不进入任何统计与溯源底账**。这是 DATA_GOVERNANCE 的合规红线在统计层的落地。
- 该常量在 `stats.py` 中以 `STATS_FILTER` 冻结，所有切片只在其上**追加** WHERE 条件，不得绕过或削弱。

## 2. 切片语义表

切片维度（API §2.11 查询参数），任选组合；语义变更须升版本（见 §5）：

| 切片 | SQL 语义 | 设计理由 |
|---|---|---|
| `category`（岗位类） | `j.job_category = %s` **精确匹配** | job_category 为 S3 规范化产出的受控枚举，精确匹配即完整 |
| `city`（城市） | `j.city ILIKE '%city%'` **子串匹配** | city 字段存在"杭州，北京"等多城并列格式，精确匹配会漏掉多城岗位 |
| `salary`（薪资段） | **区间重叠**：`j.salary_max >= band_min AND j.salary_min <= band_max` | 岗位薪资区间与查询带宽有任何交叠即计入；**带此切片时无薪资（NULL）岗位排除**——无法判定归属，宁可少算不可猜 |
| `window`（时间窗） | `j.collected_at::date BETWEEN start AND end`（**含两端点**） | 参数为 ISO 日期字符串（YYYY-MM-DD） |

薪资切片只给单边时，另一边按开区间处理（缺 min → 0，缺 max → +∞）。

## 3. frequency 公式与舍入

```
frequency = jd_count / sample_size
```

- **分子** `jd_count`：该技能（canonical_name）关联的去重岗位数（`count(DISTINCT js.job_id)`）。
- **分母** `sample_size`：**同一切片口径下**的岗位总数——即"切片内分母"，不是全市场 N。例：`--category agent_dev` 时某技能 frequency = 该技能在 agent_dev 岗位中的出现率。
- **舍入**：`round(..., 4)`，即 4 位小数。
- 注意：一个岗位通常命中多个技能，因此各技能 frequency 之和**不等于 1**，这是出现率（per-skill prevalence）而非占比分布。

## 4. 样本量守门与置信度分级（ADR-008）

数据诚实红线：系统绝不在小样本上冒充市场真相。

- **守门**：切片后 `N < min_sample`（默认 30）→ **不出统计**。
  - `skill_frequency` 返回 `status = "insufficient_sample"`（附真实 N）；
  - `create_snapshot` **不写表**（S11：统计 SQL 异常/样本不足不产出部分结果）；
  - `min_sample` 只升不降（API §2.11 允许调用方调高，不允许低于 30 绕过守门）。
- **置信度分级**（每个统计输出强制附带）：

| N | confidence |
|---|---|
| ≥ 200 | high |
| 50 ≤ N < 200 | medium |
| 30 ≤ N < 50 | low（界面须提示谨慎采信） |
| < 30 | 不输出统计 |

每个统计输出同时附带：`sample_size`、`confidence`、`window`（数据实际时间范围）、`source_distribution`（来源与 trust_tier 分布）、`method_version`。

## 5. method_version 变更纪律

- 当前版本 **s11-v1**，覆盖口径指纹：统计过滤（§1）+ 切片语义（§2）+ frequency 公式与舍入（§3）。
- **任何口径变更（含看似无害的调整，如 city 匹配方式、舍入位数）必须：先修改本文档 → 再升 `stats.py` 中 `METHOD_VERSION` → 然后才允许改代码。** 反向顺序视为违规。
- `market_snapshot` 为 append-only 历史表：每次生成插入新行（`computed_at` 区分），`method_version` 逐快照记录——口径升级后，旧版本快照仍可按原口径解读，历史趋势跨版本对比时须先核对 method_version 是否一致。

## 6. 交叉对照方法（与 MARKET_RESEARCH §2.1 的方向一致性）

用途：检验自建数据集与唯一公开量化线索（MARKET_RESEARCH §2.1，23 JD 非官方小样本）的**方向一致性**。

- **方法**：Kendall tau-a。对 14 个参考技能构成的对 `(reference_frequency, our_frequency)` 计算秩相关；**并列对不计入分子，分母为全部对数**；n < 2 无定义返回 0。
- **参考表**：`stats.py` 中 `REFERENCE`（14 技能，照抄 §2.1 频率）；`REFERENCE_TO_CANONICAL` 将参考名映射到词表 canonical_name（"向量数据库"无单一对应技能，取 Milvus/Chroma/Qdrant 三者频率**最大值**）。
- **逐技能 diff**：`diff = round(our_frequency - reference_frequency, 4)`，逐条写入报告，不做任何聚合遮蔽。
- **用途限定（硬性）**：该对照**仅用于假设检验（方向对照），不作为真值**。参考表本身是 23 JD 的非官方小样本——本项目 Market Intelligence 模块的使命正是用自建数据集把它变成可复现、可追溯的数据。tau 值低不自动意味着任何一方错误，只意味着两套样本的排序方向差异程度。

## 7. 溯源底账口径（API §2.12，skill-evidence）

- **过滤口径与统计完全一致**：同一 `STATS_FILTER` + 同一切片语义。未授权贡献**永不进底账**——"每个百分比可点击溯源到 JD 列表"的承诺必须建立在合规数据上。
- **不做样本量守门**，原因：底账是**逐条 JD 列表的罗列**（`jd_refs`：job_id / title / source_type / evidence_text / source_url / collected_at），不是统计推断。守门保护的是"频率数字"的统计可信度；"哪些 JD 支撑这个技能"是可逐条核验的事实列举，列多少条就是多少条（返回真实的 `jd_count`），不存在"样本不足"的说法。`evidence_text` 保留抽取时的原文片段，可回查 JD 原文。
- 技能名不在词表中时显式返回 `status = "unknown_skill"`（空列表），不猜测、不模糊匹配。

---

> 首跑真实数字（2026-09-02，N=50，snapshot#1，tau=0.1538）见 `docs/plans/phase4_first_run_results.md`；本文档只锁口径，不放会随数据增长而变化的数字。
