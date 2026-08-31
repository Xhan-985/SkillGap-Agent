# DATA_PIPELINE —— 数据管道设计（Phase 1）

> SkillGap Agent ｜ Phase 1 交付物
> 原则：**管道每一步可独立重跑、失败可隔离、LLM 只出现在两个受控节点（技能抽取、解释生成），其余全部确定性代码。**

---

## 1. 总览

```
┌─ 数据源 ──────────────────────────────────────────────────────┐
│  ① Public API（Adzuna，Global）                                 │
│  ② Public Job Page（公司官网招聘页人工摘录，China/Global）         │
│  ③ User Submitted JD（opt-in 匿名贡献，China 主通道）             │
│  ④ CSV / JSON 导入（社区批量贡献）                                │
└──────────────┬─────────────────────────────────────────────────┘
               ↓
S1 Ingestion（采集/接收）      ← Adzuna 拉取：代码；用户提交：用户动作
S2 Raw Staging（原始暂存）     ← 原文不动，来源九字段登记
S3 Normalization（规范化）     ← HTML 清洗/字段映射/市场与语言标记
S4 PII Detection（检测）       ← 正则规则（确定性）
S5 PII Redaction（脱敏）       ← 命中替换为标记
S6 Deduplication（去重）       ← content_hash 唯一约束
S7 Quality Validation（质检）  ← 长度/语言/岗位可识别性
S8 Skill Extraction（抽取）   ← LLM Structured Output（受控节点 1）
S9 Skill Normalization（归一） ← alias 表 + Taxonomy
S10 Job Dataset（入库）
               ↓
S11 Market Analytics（统计）   ← SQL → MarketSnapshot（分市场）
S12 Explanation（解释生成）    ← LLM 只读快照生成文本（受控节点 2）
```

**人工审核点**：S7 quarantine 队列复核、PII 抽查（DATA_GOVERNANCE §4）、E5 数据质量报告的周期性人工判读。

---

## 2. 分步规格

### S1 Ingestion（采集/接收）

| 项 | 内容 |
|---|---|
| 输入 | Adzuna API 响应（分页 job 列表）｜用户粘贴的 JD 文本 + opt-in 勾选｜CSV/JSON 文件｜人工摘录表单 |
| 输出 | RawRecord（原始载荷 + 来源九字段：source_type/source_name/source_url/collected_at/submitted_at/content_hash/license_or_usage_note/consent_status/data_quality） |
| 失败处理 | Adzuna 429/5xx → 指数退避重试 ≤3 次，仍失败记录 checkpoint 次日续拉；用户提交为空/超长 → 422 直接拒绝并提示；CSV 行级解析失败 → 该行进错误报告不中断整批 |
| 是否 LLM | 否 |
| 人工审核 | 否（数据已在源头由用户/API 提供） |
| 备注 | Adzuna 拉取由用户手动运行 ingest 命令触发（合规隔离：代码不含数据，见 DATA_GOVERNANCE §6）；请求预算遵守免费层限额（25 req/min，250 req/day），拉取节奏进配置 |

### S2 Raw Staging（原始暂存）

| 项 | 内容 |
|---|---|
| 输入 | RawRecord |
| 输出 | raw_jobs 表记录（status=pending） |
| 失败处理 | 写库失败 → 事务回滚，原始载荷留存错误队列（不丢数据） |
| 是否 LLM | 否 |
| 人工审核 | 否 |
| 备注 | 原文仅暂存；用户个人分析用原文在其会话内，贡献给市场数据集的副本走 S4/S5 脱敏（见 DATA_GOVERNANCE §3 双轨说明） |

### S3 Normalization（规范化）

| 项 | 内容 |
|---|---|
| 输入 | raw_jobs(pending) |
| 输出 | 规范化字段：title/city（Adzuna 地区码映射）/salary 区间归一（币种×汇率表快照，仅 Global 用 USD 记录原币+折算）/language（zh/en 检测，规则法）/market（china/global）/company 标准名 |
| 失败处理 | 字段缺失 → 该字段置 null + missing_field 计数（不中断）；salary 无法解析 → null；市场判定失败（语言与来源矛盾）→ 默认按来源 tier 推断并标记 ambiguous |
| 是否 LLM | 否（规则 + 映射表） |
| 人工审核 | 否 |
| 备注 | 中国市场 JD 若含少量英文技能词，不影响 market=china 判定（按 JD 主体语言） |

### S4 PII Detection（检测，仅用户贡献通道强制）

| 项 | 内容 |
|---|---|
| 输入 | 规范化后的 JD 文本 |
| 输出 | PIIFinding 列表（类型 + 位置 + 命中规则版本） |
| 失败处理 | 规则执行异常 → 整条进入 quarantine（宁可误伤不可漏过） |
| 是否 LLM | 否（正则规则库，版本化 pII_rules_version） |
| 人工审核 | 定期抽样（比例见 DATA_GOVERNANCE §4） |
| 检测范围 | 手机号（1[3-9]\d{9} 及常见变体）、邮箱、微信号提示词、QQ 号提示词、"联系人/联系电话/HR 姓名"上下文模式、身份证号 |

### S5 PII Redaction（脱敏）

| 项 | 内容 |
|---|---|
| 输入 | JD 文本 + PIIFinding |
| 输出 | 脱敏文本（命中项替换为 [PHONE_REDACTED]/[EMAIL_REDACTED]/[CONTACT_REDACTED]/[ID_REDACTED]）+ redaction_report（命中统计） |
| 失败处理 | 替换操作不可逆异常 → 整条拒绝进入市场数据集（fail-closed） |
| 是否 LLM | 否 |
| 人工审核 | 抽样 + quarantine 队列复核入口 |
| 诚实边界 | **不声称 100% 删除所有隐私**——正则 + 上下文规则 + 人工抽查三层，残余风险在文档与 UI 中明示 |

### S6 Deduplication（去重）

| 项 | 内容 |
|---|---|
| 输入 | 脱敏后文本 |
| 输出 | content_hash（对规范化文本计算）；已存在则返回已有 job_id |
| 失败处理 | hash 冲突（同 hash 不同实质内容，理论罕见）→ 人工复核队列 |
| 是否 LLM | 否 |
| 人工审核 | 冲突时 |
| 备注 | 轻度规范化后哈希（去空白/统一全角半角/大小写折叠）以提高跨源重复检出；duplicate_rate 指标进 E5 |

### S7 Quality Validation（质检）

| 项 | 内容 |
|---|---|
| 输入 | 去重通过的记录 |
| 输出 | validation_verdict（pass / quarantine / reject） |
| 规则 | 长度 50-20000 字符；语言可识别；标题非空且含岗位信号（词表命中或模式匹配）；非纯模板/广告文本 |
| 失败处理 | quarantine → 人工复核后放行或丢弃；reject → 直接丢弃并计数 |
| 是否 LLM | 否 |
| 人工审核 | **是**（quarantine 队列，MVP 为 CLI/管理页复核） |
| 备注 | invalid_jd_rate 指标进 E5 |

### S8 Skill Extraction（技能抽取 —— LLM 受控节点 1）

| 项 | 内容 |
|---|---|
| 输入 | 质检通过的 JD 文本 |
| 输出 | StructuredResult（技能名/重要度/程度词/证据片段），Pydantic Schema 校验 |
| 失败处理 | Schema 校验失败 → 同请求重试 ≤2 次（携带校验错误反馈）；仍失败 → status=extraction_failed 隔离，**不进统计**；超时 → 按超时处理跳过，标记待重试 |
| 是否 LLM | **是**（LLM Gateway 唯一入口，缓存键 = content_hash + model + prompt_version） |
| 人工审核 | 否（质量由 E1 评测集守门） |
| 备注 | 证据片段必须可在原文定位（字符串校验），不可定位即判失败 |

### S9 Skill Normalization（归一）

| 项 | 内容 |
|---|---|
| 输入 | StructuredResult（原始技能表述） |
| 输出 | skill_id 对齐（alias 表 + ESCO 锚点；词表外新词 → 候选表待人工裁决） |
| 失败处理 | 无法归一 → 进 new_skill_candidate 表（不丢弃、不静默入表）；alias 歧义（一词多技能）→ 按上下文规则取置信最高，低于阈值标记 ambiguous |
| 是否 LLM | 否（查表 + 规则）；嵌入相似度辅助仅作排序建议，不自动入表 |
| 人工审核 | **是**（新技能候选表周级裁决） |
| 备注 | 归一正确性由 E1 对抗用例守门（"LangChain vs LangChain.js 应同归一"） |

### S10 Job Dataset（入库）

| 项 | 内容 |
|---|---|
| 输入 | 全部通过项 |
| 输出 | job / job_skill / 关联 data_source 记录，status=active |
| 失败处理 | 事务失败 → 回滚重放（幂等，content_hash 兜底） |
| 是否 LLM | 否 |
| 人工审核 | 否 |
| 备注 | 来源九字段 NOT NULL 约束在此强制（DB 层） |

### S11 Market Analytics（统计）

| 项 | 内容 |
|---|---|
| 输入 | job + job_skill（active，按 market 分区查询；**排除未授权贡献数据**——`source_type='user_submitted' AND consent_status≠'market_analysis'` 永不进统计，与 DATA_MODEL §3 统计守门口径一致，B1 修复一致性传播） |
| 输出 | MarketSnapshot（scope 含 market/岗位类/城市/时间窗；sample_size；skill_frequency；来源分布；confidence 分级） |
| 失败处理 | 切片 N<30 → **不生成 snapshot**，返回"样本不足"；统计 SQL 异常 → 任务失败告警（不产出部分结果） |
| 是否 LLM | **禁止**（CI 静态检查统计模块零 LLM 依赖） |
| 人工审核 | 口径变更时 review method_version |
| 备注 | 趋势 = 多 snapshot 时间序列对比，仅在样本量足够时计算（ADR-008） |

### S12 Explanation（解释生成 —— LLM 受控节点 2，只读）

| 项 | 内容 |
|---|---|
| 输入 | 冻结的确定性快照（匹配 breakdown / ROI 表 / 频率口径）+ 用户问题 |
| 输出 | 自然语言解释文本（**禁止输出数值**，数值仅由快照携带并由 UI 渲染） |
| 失败处理 | 生成失败/超时 → 降级为模板化解释（不阻塞主流程）；解释中的百分比与 snapshot 比对不一致 → 该解释丢弃重生成 |
| 是否 LLM | **是**（只读输入，无工具、无写入权限） |
| 人工审核 | E3 评测 LLM-as-judge 抽查 |
| 备注 | Phase 8 若引入 RAG 问答，同样遵循"检索真实数据 + 引用 + 数值来自快照"约束 |

---

## 3. 管道运行模式

| 模式 | 触发 | 覆盖步骤 | 频率 |
|---|---|---|---|
| 用户贡献流（在线） | 用户提交 JD + opt-in | S1→S10 流水线内联执行，S11 夜间批量 | 实时（脱敏去重秒级） |
| 海外 Ingest 流（离线） | 用户运行 ingest 命令 | S1（Adzuna）→S3→S6→S7→S8→S10，S11 夜间批量 | 按需/每日 |
| 批量导入流（离线） | CLI import 命令 | 同上（CSV/JSON 源） | 按需 |
| 统计快照流（定时） | 定时任务 | S11 | 每日 |
| 评测回流 | 用户反馈/坏例 | 坏例 → evaluation_sample（case promotion） | 持续 |

**幂等性约定**：S1-S10 任意步骤可重跑，content_hash 保证不重复入库；S11 快照按 (scope, window) 唯一，重算覆盖。

---

## 4. LLM 使用边界总表（三层分离落地）

| 层 | 步骤 | LLM 参与 |
|---|---|---|
| Deterministic | S1-S7、S9、S10、S11 | **零**（CI 静态检查） |
| LLM | S8（抽取）、S12（解释） | 仅此两处，输出必过校验，禁改数值 |
| Evidence | S5/S8/S10 产出的证据字段、S11 的 sample_size/来源分布 | 数据库承载，供 API 全链路回查 |
