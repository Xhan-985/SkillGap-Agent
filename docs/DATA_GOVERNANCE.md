# DATA_GOVERNANCE —— 数据治理与合规（Phase 1）

> SkillGap Agent ｜ Phase 1 交付物
> 硬约束声明：**SkillGap Agent 不通过爬虫获取 BOSS 直聘、牛客、拉勾、智联招聘、猎聘等任何招聘平台数据。本约束为项目红线，不是需要绕过的问题。**

---

## 1. 数据来源全景

| 来源 | source_type | Trust Tier | 市场 | 采集方式 |
|---|---|---|---|---|
| Adzuna 公开 API | public_api | **Tier A** | Global | 用户自行运行 ingest 命令，遵守免费层限额 |
| 公司官方招聘页 | public_job_page | **Tier A** | China/Global | 人工浏览 + 摘录，记录 source_url |
| 用户主动粘贴 JD | user_submitted | **Tier B** | China 主 | 用户动作 + opt-in 匿名贡献 |
| CSV/JSON 导入 | csv_import / dataset_builtin | **Tier C** | China 主 | 社区批量贡献，过同一管道 |

**用户主动提交 ≠ 平台自动抓取**：用户在招聘软件里自行看到岗位后复制粘贴，属于用户对自己浏览内容的处置；平台不对招聘平台发起任何自动化请求。二者在数据模型（consent_status 字段）与治理上严格区分。

## 2. 来源登记（每条 Job 强制九字段）

`source_type` ｜ `source_name` ｜ `source_url` ｜ `collected_at` ｜ `submitted_at` ｜ `content_hash` ｜ `license_or_usage_note` ｜ `consent_status` ｜ `data_quality`

- DB 层 NOT NULL + CHECK（public_job_page 必须 source_url；user_submitted 必须 consent_status）
- 统计输出附来源分布（Tier A/B/C 占比），不允许把"用户提交 1 条 JD"与"公开 API 大批量数据"不加区分地混算（ADR-002）

## 3. 用户贡献 JD 机制

```
用户粘贴 JD → 即时 JD Analysis（个人价值，先交付）
        ↓
分析结果页询问：「匿名贡献到市场数据集？」（默认不勾选，明确 opt-in）
        ↓ 同意
PII Detection（正则规则，pII_rules_version 版本化）
        ↓
PII Redaction（[PHONE_REDACTED] / [EMAIL_REDACTED] / [CONTACT_REDACTED] / [ID_REDACTED]）
        ↓
Content Hash → Deduplication → Quality Validation → Skill Extraction
        ↓
Market Dataset（consent_status=market_analysis）
```

- **匿名性**：不记录贡献者身份，仅保留匿名计数；不存 IP（本地部署场景天然满足）
- **删除机制**：贡献成功时生成一次性显示的 deletion_code（哈希存储）；用户凭 code 可删除该条贡献——无账号体系下满足可删除性
- **个人分析 vs 贡献数据双轨**：用户会话内的 JD 原文仅服务本人分析；进入市场数据集的副本必为脱敏后文本

## 4. PII 处理

| 项 | 设计 |
|---|---|
| 检测对象 | 手机号、邮箱、联系人姓名（上下文模式）、微信号、QQ 号、身份证号、公司内部敏感串 |
| 检测方法 | 确定性正则规则库（版本化），**非 LLM**——可审计可回放 |
| 脱敏方法 | 命中替换为类型标记（见 §3），保留可读性用于技能抽取 |
| 诚实边界 | **不声称 100% 删除所有个人隐私**。三层防线：规则（主体）→ 人工抽查（按贡献量的固定比例抽样复核）→ quarantine 人工复核队列 |
| 漏检处置 | 发现漏检 → 该样本人工修正 + 规则版本升级 + E5 指标重跑 |
| 用户简历 | 不进入任何市场统计；仅本地用户本人可见；保留策略见 §5 |

## 5. 数据保留与删除策略

| 数据类别 | 保留策略 | 删除机制 |
|---|---|---|
| 用户简历/画像 | 会话级保留，默认 30 天不活动过期 | 用户可随时删除（无 confirm 即删 + 二次确认 UI） |
| 用户贡献 JD（脱敏后） | 长期保留（市场统计需要时间跨度） | deletion_code 删除（§3） |
| Raw 暂存数据（S2） | 处理完成 7 天后清理 | 定时任务物理删除 |
| 匹配/建议结果 | 保留供评测回归 | 随画像删除级联 |
| 评测标注集 | 版本化长期保留 | 不删除（研究资产，已匿名） |

## 6. 外部 API 条款核查结论（2026-08-31 核查）

| API | 结论 | 依据 |
|---|---|---|
| **Adzuna** | **采用（Tier A，Global Market 唯一首发源）**。免费层 25 req/min、250 req/day、2500 req/month；覆盖 16+ 国（无中国大陆/香港数据）；字段质量高（title/company/location/salary 结构化）。**义务**：展示层需带 "Jobs by Adzuna" 归属标识并链接 adzuna.co.uk；**限制**：商业/政府/学术组织存在 14 天试验期条款，禁止以原始或聚合形式交付持续工作——因此本项目定位为个人研究与开源工具，**开源仓库只分发连接器代码、不分发 Adzuna 数据本身**，数据由最终用户自行运行 ingest 获取并自行遵守条款 | developer.adzuna.com/docs/terms_of_service |
| Remotive | 备选（Should Have）：公开免费、强制反链 Remotive；建议 ≤4 次/天、数据延迟 24h、仅远程岗位 | remotive.com/remote-jobs/api |
| USAJOBS | **排除**：条款明确限制数据仅限申请表所列用途，禁止出租/交易/衍生作品，聚合统计有合规风险 | developer.usajobs.gov/guides/terms-of-use |
| Greenhouse / Lever 公开 board API | 暂缓：数据质量有限（Greenhouse 无 salary 字段）且无官方公开条款页；公司招聘页人工摘录已覆盖此需求 | boards-api.greenhouse.io；api.lever.co/v0/postings |
| Hacker News（Algolia） | **排除**：评论版权归属作者，聚合使用风险高且无结构化字段 | — |

> 核查结果为 2026-08-31 快照；接入任何新源前须重查其当时有效条款（ADR-002 复议流程）。

## 7. Attribution 与展示义务

- 使用 Adzuna 数据的界面：显示 "Jobs by Adzuna"（链接 adzuna.co.uk）+ 数据窗口说明
- 公开页面摘录数据：统计详情页可回查 source_url
- 用户贡献数据：标注 "community contributed（匿名）"及 consent 状态
- 任何对外引用本数据集的输出（截图/报告）：附带样本量、窗口与来源分布

## 8. 反爬与合规红线清单

**永久禁止**：开发针对 BOSS 直聘/牛客/拉勾/智联/猎聘等平台的爬虫；绕过登录限制、验证码、反爬机制；模拟用户行为批量采集；未经许可抓取受限制数据；以"需要真实国内岗位数据"为由突破以上任何一条。

**违反后果**：任何 PR 触及红线即拒绝合并（CI 层无爬虫依赖检查 + 代码评审）。

**中国岗位数据合法获取路径（本项目采用）**：用户主动粘贴 JD + 公司官方招聘页人工浏览摘录（记录 URL）+ 用户/社区主动提供的 CSV/JSON 批量数据。
