# DATA_COLLECTION —— 首批人工 JD 数据集采集模板与规范（Phase 2 交付物）

> SkillGap Agent ｜ 2026-08-31 ｜ 配合 data/collect_template.csv 使用
> 红线（DATA_GOVERNANCE §8）：禁止任何平台爬虫/绕过登录/模拟用户行为。本规范只覆盖合规通道。
> 数据模型结论：Phase 2 schema（migration 001）**完全支持本批数据，无需任何数据库改动**。19 个模板列全部映射到管道 RawRecord/SourceFields → job 表。

## 0. 模板文件与格式要求

- 模板：`data/collect_template.csv`（19 列，含 2 条示例行）
- **仅支持 CSV / JSON**（导入器 `parse_file` 只认这两种后缀）；Excel 用户请在 Excel 中编辑、最后"另存为 → CSV UTF-8"
- 编码 UTF-8（带不带 BOM 均可，读取用 utf-8-sig）
- 含逗号的字段用双引号包裹；`soft_requirements`/`skills` 两列填 JSON 数组，JSON 内的双引号在 CSV 中写成两个双引号（Excel 会自动处理）
- `raw_text` 允许换行（字段用双引号包裹即可）；为降低 Excel 换行出错风险，也可把换行替换为空格后再填

## 1. 通道定位（本批怎么选）

| 通道 | source_type / source_name | 适用场景 | PII 自动脱敏 |
|---|---|---|---|
| 公司官方招聘页摘录（**主通道**） | public_job_page / company_career_page | 浏览公开页→复制→当场记录 URL 与时间 | **否**（Tier A 假设，须人工清理，见 §5） |
| 自建 Demo 批次 | dataset_builtin / demo_dataset | 自拟/改写的合规样例 | 是 |
| 社区批量 | csv_import / community_csv | 他人提供的 CSV 批量贡献 | 是 |
| 用户粘贴贡献 | user_submitted / user_contribution | **不走 CSV**——过 CLI `skillgap contribute`（consent + 删除凭证由 CLI 处理） | 是 |

注意：`source_name` 必须是 `data_source` 表已注册的值（上述五个，`skillgap seed` 自动注册），未注册的来源整批报错。中文 JD 走 `company_career_page`/`community_csv`/`demo_dataset` 均可；**英文 JD 只能走 `company_career_page`**（其余三个来源 covers_market=china，会被判入 china 市场）。

## 2. 字段总表：人工填 vs 自动生成 vs 可空

| 列 | 谁来填 | 可空 | 格式/取值 | 说明 |
|---|---|---|---|---|
| title | **人工（必填）** | 否 | 岗位标题原文，须含岗位信号词（工程师/开发/研发/算法/engineer/developer/manager 等，否则质检 quarantine） | 保留原文，不改写 |
| raw_text | **人工（必填）** | 否 | JD 全文，**50–20000 字符**（超范围 quarantine）；直接复制粘贴 | 含岗位信号词与技能描述；PII 清理见 §5 |
| source_type | **人工（必填）** | 否 | 5 枚举之一（见 §1） | |
| source_name | **人工（必填）** | 否 | 已注册来源名（见 §1） | |
| collected_at | **人工（必填）** | 否 | YYYY-MM-DD | 浏览/收集当天当场记录 |
| source_url | 人工（条件必填） | 是 | 完整 URL | **public_job_page 必填**（数据库 CHECK）；其余通道可空 |
| company | 人工 | 是 | 公司名原文 | 空则 company_id 为 NULL；同名字符串自动归并到同一 company |
| city / country / region | 人工 | 是 | 如 北京 / 中国 / 华北 | 建议尽量填 city（市场切片统计用） |
| salary_min / salary_max | 人工 | 是 | 整数；中国岗位填**月薪·元**（如 15000） | 留空时管道自动从 raw_text 解析（支持"15k-25k""1.5万-2.5万"） |
| salary_currency | 人工 | 是 | CNY / USD / EUR 等 | 填了 salary 才需要 |
| job_category | 人工 | 是 | 8 枚举：ai_application_dev / agent_dev / llm_fullstack / mcp_dev / ai_platform / python_ai_dev / dify_dev / other | 留空由规则从标题+正文前 500 字自动归类 |
| soft_requirements | 人工 | 是 | JSON 数组：`[{"type":"experience","value":"1-3年","evidence_text":"..."}]`；type 仅 experience/education/language | evidence_text 须为原文片段 |
| skills | 人工（**强烈建议**） | 是 | JSON 数组，每项：raw_name / importance（must_have 或 nice_to_have）/ intensity（精通/熟练/熟悉/了解，可省）/ evidence_text | 见 §6；本批定位 = 人工标注集 |
| consent_status | 人工（固定值） | 否（默认 none） | 公开页/自建/社区一律 `none`；`market_analysis` 仅 user_submitted（CLI 通道，CSV 中禁用） | |
| data_quality | 人工 | 否（默认 auto_passed） | 人工收集填 `human_reviewed`；逐条完整核对过九字段可填 `verified` | **勿用 auto_passed**（那是管道自动质检的语义） |
| license_or_usage_note | 可空 | 是 | 来源级许可已存 data_source 表 | 一般留空 |
| submitted_at | 可空 | 是 | 仅 user_submitted 通道有语义 | 一律留空 |
| content_hash | **系统自动** | — | 管道在（脱敏后）文本上计算 sha256 | 模板中无此列，**不要手工填** |
| market | **系统自动** | — | china / global：来源 covers_market 权威；both 时按语言（zh→china，en→global） | 不要试图手工控制 |
| language | **系统自动** | — | zh / en（按 CJK 字符占比 ≥30% 判 zh） | |
| company_id / job 的其余字段 | **系统自动** | — | 由管道从上述列生成 | |

## 3. 九字段处理速查

`source_type / source_name / source_url / collected_at / submitted_at / content_hash / license_or_usage_note / consent_status / data_quality`：

- 前五 + 后四中，人工只负责 source_type、source_name、source_url（public_job_page 必填）、collected_at、consent_status（固定 none）、data_quality（human_reviewed）
- **content_hash 系统自动**（收集时无需、也无法填）
- submitted_at / license_or_usage_note 本批一律留空

## 4. 去重规则

1. **系统级（自动）**：管道对脱敏后文本做 NFKC（全角→半角）→ casefold → 空白折叠 → sha256，`job.content_hash` 唯一约束。全角/半角、大小写、换行空白差异都会被判同文 → 记 `duplicate`（**幂等：重复导入不算错误，重跑安全**）
2. **人工级（收集时遵守）**：
   - 同一 JD 被多平台转发 → 只录一次（优先公司官方页，source_url 记官方页）
   - 同公司同名岗位不同城市 → 文本不同，各录一条
   - 不同公司用同一份模板 JD → 文本相同会被系统去重，只留先导入的那条；**收集时也只挑一家**（避免浪费配额）
   - 警惕模板化文本：≥8 行且行重复率 >50% 会被质检 quarantine（template_like）

## 5. PII / 个人信息脱敏要求

- **public_job_page 通道不自动脱敏**（管道仅对 user_submitted/csv_import/dataset_builtin 强制走 PII 规则）——所以：
  - 复制 JD 时**先删除** HR 联系方式（邮箱/手机号/微信号/QQ 号/"联系人：张三"字样）
  - 若删除会破坏句子结构，用管道同款标记替换：`[EMAIL_REDACTED]` `[PHONE_REDACTED]` `[WECHAT_REDACTED]` `[QQ_REDACTED]` `[CONTACT_REDACTED]`
- csv_import / dataset_builtin 通道：管道自动检测并替换上述标记（fail-closed），但人工先清理一遍更稳
- **不收集**：简历、身份证号、任何非 JD 原文的个人信息；公司名/城市/薪资不是 PII（是统计单位）
- 首批目标：抽查 20 条中 0 条含未脱敏联系方式（§4 抽样核对）

## 6. skills 列填写策略（本批的核心价值）

本批 200–300 条定位 = **Tier A 人工标注集**（同时充当 E1 评测集扩充素材与市场统计种子），推荐**每条人工标注 skills**：

- 每条 3–8 个技能，优先使用词表（taxonomy/data/skills_v1.csv 的 canonical_name，如 RAG / Python / LangChain / Docker）
- `evidence_text` **必须是 raw_text 中的原文连续片段**（管道做字符串定位校验，不通过 → 整条 extraction_failed，不入 job_skill）
- 词表外的技能名照填——管道会把无法归一的放入 `new_skill_candidate`（周级人工裁决），**不影响该条入库**
- importance：岗位硬性要求 = must_have；"优先/加分/了解" = nice_to_have
- 若某条实在无法判断，宁可留空整列（该条入库但无 job_skill 行）

**已识别的管道限制（待你确认，未改任何代码）**：CSV 批次（public_job_page/csv_import/dataset_builtin）若不填 skills，管道不会为其标记 `extraction_status=pending`（该标记仅 user_submitted 通道），因此 Phase 3 的 `backfill-extraction`（LLM 批量抽取）**不覆盖 CSV 批次**。若你希望"只收集原文、之后用 LLM 批量抽取"，需要小改 pipeline（一行：无标注的 CSV 批次也标 pending）——确认后我再动代码。

## 7. 完整示例（一条）

CSV 行（模板第 1 行，字段逐项解读见右）：

```csv
title,company,city,country,region,salary_min,salary_max,salary_currency,job_category,raw_text,soft_requirements,skills,source_type,source_name,source_url,collected_at,submitted_at,consent_status,data_quality
AI 应用开发工程师,示例公司,北京,中国,华北,15000,25000,CNY,ai_application_dev,"岗位职责：负责大模型应用开发，搭建 RAG 检索链路与 Agent 编排，优化 Prompt 工程。任职要求：1-3年大模型应用开发经验，熟悉 LangChain、LangGraph，精通 Python，了解 Docker 部署。","[{""type"":""experience"",""value"":""1-3年"",""evidence_text"":""1-3年大模型应用开发经验""}]","[{""raw_name"":""RAG"",""importance"":""must_have"",""intensity"":""熟悉"",""evidence_text"":""搭建 RAG 检索链路""},{""raw_name"":""Python"",""importance"":""must_have"",""intensity"":""精通"",""evidence_text"":""精通 Python""},{""raw_name"":""Docker"",""importance"":""nice_to_have"",""intensity"":""了解"",""evidence_text"":""了解 Docker 部署""}]",public_job_page,company_career_page,https://hr.example.com/job/1001,2026-08-31,,none,human_reviewed
```

解读：中文 JD→market=china、language=zh（系统判）；job_category 显式填 ai_application_dev（也可留空自动归类）；3 个技能全部来自词表，evidence 均可在原文中逐字找到；LangChain/LangGraph 未标注不影响入库（可后续 LLM 补抽或人工补标）；consent=none（公开页摘录）；data_quality=human_reviewed。

JSON 等价格式（同样可导入，raw_text 多行时更稳）：

```json
[{
  "title": "AI 应用开发工程师",
  "company": "示例公司", "city": "北京", "country": "中国", "region": "华北",
  "salary_min": 15000, "salary_max": 25000, "salary_currency": "CNY",
  "job_category": "ai_application_dev",
  "raw_text": "岗位职责：负责大模型应用开发，搭建 RAG 检索链路与 Agent 编排，优化 Prompt 工程。任职要求：1-3年大模型应用开发经验，熟悉 LangChain、LangGraph，精通 Python，了解 Docker 部署。",
  "soft_requirements": [{"type": "experience", "value": "1-3年", "evidence_text": "1-3年大模型应用开发经验"}],
  "skills": [
    {"raw_name": "RAG", "importance": "must_have", "intensity": "熟悉", "evidence_text": "搭建 RAG 检索链路"},
    {"raw_name": "Python", "importance": "must_have", "intensity": "精通", "evidence_text": "精通 Python"},
    {"raw_name": "Docker", "importance": "nice_to_have", "intensity": "了解", "evidence_text": "了解 Docker 部署"}
  ],
  "source_type": "public_job_page", "source_name": "company_career_page",
  "source_url": "https://hr.example.com/job/1001", "collected_at": "2026-08-31",
  "consent_status": "none", "data_quality": "human_reviewed"
}]
```

## 8. 200–300 条分布方案（目标 250）

| 维度 | 分布 | 条数 |
|---|---|---|
| **岗位类别** | ai_application_dev 55 / agent_dev 40 / ai_platform 35 / llm_fullstack 30 / python_ai_dev 30 / other（Java 后端等转型对照岗）35 / dify_dev 15 / mcp_dev 10 | 250 |
| **市场/语言** | china（中文）70% ≈175 / global（英文，走 company_career_page）30% ≈75 | 250 |
| **公司多样性** | ≥40 家公司；单家公司 ≤12 条（≈5%）；大厂/初创/AI 应用公司/外企混合 | — |
| **城市** | 北上深杭 ≥50%；新一线（成都/武汉/西安/南京等）≈30%；远程/其他 ≈20%（global 条目不受此限） | — |
| **技能标注** | 每条 3–8 个技能；全批 must_have/nice_to_have 比例 ≈ 7:3 | — |
| **薪资字段** | 填率 ≥60%（供薪资分布统计；原文无范围就留空） | — |

原则：**任何单一类别不超过 22%**，保证 S11 频率统计不偏斜；agent_dev/ai_application_dev（你的目标方向）适度超配，other 保留作对照。

## 9. 分批纪律（MVP §3）

- 分 5 批 × 50 条，**每批 50 条后跑一次**：
  `skillgap import --file data/batch_N.csv` → `skillgap stats --market china` → `skillgap quality-report`
- 词表校准：频率统计与词表对照；新技能进 `new_skill_candidate`，人工周级裁决
  （更新 skills_v1.csv → taxonomy_version 注记 → 重新 `skillgap seed`）
- 止损线：2 周 <100 条 → 缩小到"AI 应用开发"单一切片（MVP §6）

## 10. 抽样核对（Phase 2 验收：抽样 20 条人工核对字段）

每批导入后从 `job` 表随机抽 20 条（`ORDER BY random() LIMIT 20`），逐条核对：
九字段完整、market 与预期一致、market_ambiguous 不为 true、skills 的 evidence_text
可在 raw_text 中定位、无未脱敏联系方式。发现偏差 → 记入 §12。

## 11. Adzuna（Global，另行操作，不占本批配额）

`skillgap ingest-adzuna --country gb --query "LLM OR RAG OR AI engineer" --max-results 500`
- 免费层 250 req/day（本地额度守卫自动拦截超额）
- 仓库**不分发** Adzuna 数据；数据只存本地库
- 展示引用时必须带 "Jobs by Adzuna" 归属

## 12. 收集日志（执行时逐批追加）

| 批次 | 日期 | 条数 | 导入结果（inserted/dup/quarantine） | 抽样核对 | 备注 |
|---|---|---|---|---|---|
| （待填） | | | | | |
