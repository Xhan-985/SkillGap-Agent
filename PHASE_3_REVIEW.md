# PHASE_3_REVIEW —— Phase 3 完成自检（六维）

> 状态：**PASS WITH RISKS**（代码与评测管道全绿 133 项测试；风险 = 真实 LLM 基线跑分未执行——LLM_API_KEY 未配置，属用户执行项，见 §4）
> 验收：ROADMAP Phase 3 验收逐项核验结果（见 §2 表）
> 日期：2026-08-31 ｜ 测试：133 passed（pytest 全量，PostgreSQL 经 docker compose）

## 1. 交付物清单（对照 ROADMAP Phase 3 产出）

- [x] LLM Gateway（Provider 抽象 + DeepSeek 单实现 + DB 缓存 + 重试）——src/skillgap/llm/（provider.py / gateway.py；缓存键 sha256(model + canonical messages)）
- [x] 抽取 Schema（Pydantic：JDExtraction / SkillAnnotation / SoftRequirement）——models.py；migration 003（llm_cache + eval_run）
- [x] alias 归一化管道——复用 Phase 2 ingest/extract.py（查表，无 LLM）
- [x] 证据可溯校验——llm_extractor._validate_evidence（字符串定位，规范化比较）
- [x] E1 标注集 v1（20 条：17 中文 + 3 英文，ground truth 全部词表 canonical_name）——data/eval/e1_seed_v1.json + eval/seed.py（幂等入库）
- [x] P/R/F1 计算 + 证据可溯率 + 阈值判定 + eval_run 回归历史——eval/e1.py
- [x] Prompt 版本管理——extract/prompt.py（PROMPT_VERSION=v1，入 eval_run/llm_cache；few-shot 与评测集严格分离）
- [x] JD Analyzer 服务（API §2.1 结构，无状态不落库）+ Phase 2 遗留回填——extract/analyzer.py
- [x] CLI 三命令（jd-analyze / eval-e1 / backfill-extraction；无 key 时 rc=2 干净退出，key 检查先于任何副作用）——cli.py
- [ ] 首轮真实基线报告——待 LLM_API_KEY 配置后 `skillgap eval-e1`（评测器/阈值/入库已就绪）

## 2. 验收核验

| 验收项 | 结果 | 证据 |
|---|---|---|
| E1 F1 ≥ 0.75（Warn 线起步） | ⏳ | 评测器 + 阈值（pass≥0.85 / warn≥0.75 / block<0.75）+ eval_run 历史就绪；真实跑分待 key（用户决策：DeepSeek） |
| 证据可溯率 100% | ✅ | 双层防线：抽取器逐条 locate_evidence 校验（不可定位触发对话式纠错重试）；E1 证据可溯率 <100% 一票 block——test_e1.py::test_evidence_rate_is_hard_requirement |
| 失败用例明示不静默 | ✅ | 超长/过短 → JDValidationError（test_analyzer）；无技能 JD → skill_count=0 显式输出；抽取重试耗尽 → ExtractionFailed（不降级不静默，API.md §2.1 LLM_EXTRACTION_FAILED 语义）；网络/HTTP 错误 → LLMError 明示 |
| Prompt 版本管理 | ✅ | PROMPT_VERSION 常量冻结入 llm_cache/eval_run；test_prompt.py |

## 3. 六维自检

### Product（解决什么）
"粘贴 JD → 结构化结果"闭环可用：`skillgap jd-analyze --file x.txt --title t` 输出 API §2.1 契约结构（job 确定性字段 + core/secondary skills 带证据 + soft_requirements + extraction_meta 含 model/prompt_version/latency/tokens）。Phase 2 遗留的 pending 抽取可 `backfill-extraction` 回填。

### Engineering（过度设计？）
新增 2 张表全部来自计划冻结的 migration 003；新增 5 个模块按依赖单向分层（analyzer → extractor → gateway → provider；eval 只读消费）。零新依赖（httpx 复用，不加 openai SDK——用户决策 Q4）。执行期对计划的修正：run_e1 的 prompt_version/model 从 extractor.gateway 推导（CLI 无需重复传参）、CLI 未加计划中的 `--limit` 死参数、缓存命中不重复计费调用。无范围扩张。

### AI（LLM 滥用？）
LLM 仅一个出口：S8 技能抽取（Structured Output，temperature=0）。market/language/job_category 由确定性规则计算（三层分离：LLM 不做统计、不改数值）；E1 指标全部集合运算与程序校验（红线：LLM 不参与指标计算——EVALUATION_PLAN §1.2）。缓存缓解成本（同模型同输入幂等，ADR-009）。

### Data（真实可溯？）
抽取结果每条技能带 evidence_text 且必须可在 JD 原文定位（规范化字符串匹配，容忍全角/空白差异）；不可定位即整体失败重试。词表外抽取不静默入统计，进 new_skill_candidate（周级裁决）。

### Evaluation（可验证？）
E1 评测器口径冻结：micro P/R/F1（池化去重）+ macro F1 + 重要度准确率 + 样本级证据可溯率；阈值预声明跑分前冻结（f1 与 recall 双闸）；每次跑分入 eval_run（版本三元组 + 指标），回归历史可查。测试 133 项全绿（含：空抽取 precision=1 无误报约定、失败样本计漏不中断、词表外不计误报、缓存命中幂等、重试计数=首次+2）。

### Resume（可讲什么）
"我实现了 LLM Gateway 防腐层（Provider 抽象 + DB 响应缓存 + 指数退避重试），技能抽取用 Structured Output + 证据原文可溯程序校验（不可定位即失败），并建了 20 条人工标注的 E1 评测集与冻结阈值的回归评测器——Prompt 任何变更都有 F1 历史可比对。"

## 4. 遗留与移交 Phase 4

- **真实基线跑分**（用户执行项）：.env 配置 `LLM_API_KEY`（DeepSeek）→ `skillgap eval-e1`；首轮 F1 预期 0.7-0.9，<0.75 时按 EVALUATION_PLAN §7 失败分诊（Prompt 措辞/词表覆盖）迭代，不放宽阈值
- 标注集从 20 条种子扩展至 50-100 条（首批真实 JD 收集后进 v2，不静默改 v1——用户决策 2026-08-31）
- 抽样 20 条人工核对（沿 Phase 2 遗留，首批数据入库后执行）
- raw_jobs 7 天清理定时化（DATA_GOVERNANCE §5；当前为 CLI 手动，随 Phase 11 CI/调度统一处理）
- Phase 8 复议点：E1 达标后评估是否需要 few-shot 增强（当前 v1 单示例）
