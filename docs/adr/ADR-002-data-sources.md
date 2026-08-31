# ADR-002：为什么采用 Public API + Public Job Pages + User Submitted JD？

状态：**已接受（Phase 1 冻结）** ｜ 日期：2026-08-31

## Context

禁止爬虫（ADR-001）之后，系统仍需要"足够真实、可追溯、合法来源"的 JD 数据支撑市场统计。Phase 1 需求要求设计三通道数据源架构并建立 Trust Model（Tier 分级），且中国/全球市场必须分离。2026-08-31 完成海外公开 API 条款核查（DATA_GOVERNANCE §6）：Adzuna 免费层 25 req/min、250 req/day、覆盖 16+ 国（无中国数据）、强制 "Jobs by Adzuna" 归属、商业/政府/学术用途有 14 天试验期条款；USAJOBS 条款禁止聚合衍生；Remotive 限制 4 次/天。

## Options

| 选项 | Pros | Cons |
|---|---|---|
| A. 单一 Adzuna 源（自动化优先） | 稳定、可自动化、结构化好（salary 字段） | 无中国数据——核心市场为零；条款限制聚合交付；单一源风险 |
| B. 纯用户提交（中国优先） | 与红线最兼容；中国数据真实 | 冷启动慢；单人项目难以积累；无海外基准 |
| C. 三通道混合 + Tier 分级 + 市场分离 | 中国（B 通道主）与全球（A 通道主）各自有稳定供给；来源透明可审计；单一源失效不致命 | 管道复杂度上升（去重/质检/PII 必须跨源统一）；需要治理文档 |
| D. 加接入 Greenhouse/Lever/USAJOBS 等 | 数据更多样 | Greenhouse/Lever 无官方公开条款页（法律风险）；USAJOBS 明确禁止聚合统计使用——均已排除/暂缓（核查结论） |

## Decision

**选择 C。** 数据源与分级：

- **Tier A（公开 API + 公司官方招聘页）**：Adzuna（Global 专用，用户自行运行 ingest、遵守 attribution 与额度）｜公司招聘官网人工摘录（记 source_url）
- **Tier B（用户主动提交）**：opt-in 匿名贡献（中国市场主通道，含 PII 脱敏管道）
- **Tier C（导入/内置）**：CSV/JSON 社区贡献 + Demo Dataset
- **市场分离**：China Market = Tier B/A(中文页面)；Global Market = Adzuna——统计永不混算，DB 与服务层双保险
- **Adzuna 合规隔离**：开源仓库只分发连接器代码，不分发 Adzuna 数据；展示层带归属标识

## Consequences

- 正面：两市场各有稳定供给；来源九字段 + Tier 分布使统计可审计；Adzuna 条款风险被"代码与数据分离"策略隔离
- 负面：海外数据不能推断中国市场（只能作参考基准）；管道需维护 4 种入口的一致质检

## Reversibility

撤销成本：**低**（各通道独立，增删不伤核心）。
复议触发条件：任一外部源条款变更（data_source.terms_checked_at 过期即触发重查）；出现官方授权的中国 JD 数据源。
