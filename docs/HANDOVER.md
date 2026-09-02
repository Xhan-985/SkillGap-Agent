# SkillGap Agent —— 项目交接文档

> 更新：2026-09-02 ｜ 代码状态：56 commits（master，仅本地）｜ 测试：200 passed

## 1. 项目一句话

**SkillGap Agent**（原暂定名 JobLens）：证据化技能决策系统——不是简历匹配工具。核心链路：收集中文 AI 岗位 JD → 技能抽取（带原文证据）→ 市场统计 → 候选人画像 → Skill Gap 量化 → 可解释匹配 → ROI 学习建议。

差异化四支柱：自建数据集 + 证据化画像 + ROI 优先级 + 三层评测。定位与决策依据见 `docs/PRODUCT_SPEC.md`、`docs/ROADMAP.md`。

## 2. 当前进度

```
Phase 0  市场与竞品研究          ✅ 完成（10 份研究文档）
Phase 1  需求冻结 + 架构设计      ✅ 完成（ADR-001~010，16 端点契约）
Phase 2  数据模型 + 管道 + 数据集 ✅ 代码完成；数据收集进行中（批次 1/4-5 已入库）
Phase 3  JD Analyzer + LLM 抽取  ✅ 完成（E1 基线 2026-09-02：F1=0.914 PASS，eval_run#2）
Phase 4  Market Intelligence     ✅ 完成（2026-09-02；snapshot#1 已产出，tau=0.1538）
Phase 5-11                       ⬜ 未开始（下一步 Phase 5 Candidate Profile）
```

阶段验收记录：根目录 `PHASE_1_REVIEW.md` / `PHASE_2_REVIEW.md` / `PHASE_3_REVIEW.md` / `PHASE_4_REVIEW.md`（六维自检 + 验收核验表）。

## 3. 技术栈与架构

| 层 | 选型 | 说明 |
|---|---|---|
| 语言 | Python 3.12+（项目 `.venv`） | 入口 `skillgap` CLI（pyproject scripts） |
| 数据库 | PostgreSQL 16 + pgvector（Docker） | `pgvector/pgvector:pg16`；pgvector 索引 Phase 8 才建（ADR-004） |
| LLM | DeepSeek（deepseek-chat） | OpenAI-compatible 直连 httpx，**不用 openai SDK**（用户决策 Q4） |
| 测试 | pytest（需真实 PostgreSQL 跑 `skillgap_test` 库） | 177 项，全部本地可跑 |

**三层分离纪律（全局红线）**：LLM 只做抽取和解释，统计/评分/ROI 数值全部 SQL 与纯函数计算；评测指标 LLM 不参与。CI 计划静态检查守门。

**数据三通道**：Adzuna（海外，public_api）/ 公司页面人工摘录（public_job_page，当前主通道）/ 用户 opt-in 贡献（user_submitted）。China/Global 市场强分离（DB CHECK + 断言双保险）。

## 4. 环境从零跑通

```powershell
# 1. 数据库（docker-compose.yml：postgres + redis）
docker compose up -d postgres

# 2. Python 环境（项目根）
#    .venv 已存在；重建：pip install -e ".[dev]"
# 3. .env（参考 .env.example）
#    DATABASE_URL / TEST_DATABASE_URL 必填
#    ADZUNA_APP_ID / ADZUNA_APP_KEY（海外拉取才需要）
#    LLM_API_KEY（DeepSeek，jd-analyze / eval-e1 / backfill 才需要）

# 4. 建库 + 初始化
& .venv\Scripts\skillgap.exe db-upgrade    # 应用 migrations/*.sql
& .venv\Scripts\skillgap.exe seed          # 词表 + 来源注册表（幂等）

# 5. 测试（注意：本机默认临时目录权限异常，必须带 --basetemp）
& .venv\Scripts\python.exe -m pytest tests/ -q --basetemp="E:\codexproject\SkillGap Agent\.pytest_tmp"
```

## 5. 代码结构导览

```
src/skillgap/
  cli.py              # 全部 CLI 入口（14 个子命令）
  config.py           # pydantic-settings（.env 优先）
  db.py / models.py   # 连接 + Pydantic 契约
  ingest/             # Phase 2 数据管道
    collector.py      #   交互式收集器（当前主力工具）
    importer.py       #   CSV/JSON 解析（中文表头映射）
    pipeline.py       #   S2-S10 编排（去重/质检/PII/入库）
    normalize.py      #   规范化（语言/市场/薪资/类别归类）
    pii.py quality.py #   PII 规则库 / 质检 quarantine
    adzuna.py contribute.py  # 海外拉取 / 匿名贡献通道
    extract.py        #   手工标注通道 + alias 归一化
  extract/            # Phase 3 LLM 抽取
    prompt.py         #   PROMPT_VERSION=v1（变更须跑 eval-e1 回归）
    llm_extractor.py  #   Structured Output + 证据定位校验 + 对话式重试
    analyzer.py       #   analyze_jd()：确定性字段 + LLM 抽取
  llm/                #   provider.py（httpx 重试）/ gateway.py（DB 缓存）
  eval/               #   e1.py（P/R/F1 + 阈值 + eval_run 历史）/ seed.py
  taxonomy/           #   词表 v1.4（47 技能 + alias）+ skill_relations
  stats.py            #   Phase 4 市场统计：切片频率/快照/溯源/交叉对照（零 LLM，守卫测试锁定）
                      #   口径文档 docs/STATS_METHOD.md；method_version=s11-v1
  quality_metrics.py  #   E5 数据质量报告
migrations/           # 001 init / 002 batch error_count / 003 llm_cache+eval_run
docs/                 # 全部设计文档 + adr/（10 份 ADR）+ plans/
tests/                # 24 个测试文件，conftest 起真实 PG 测试库
```

依赖方向（冻结）：`analyzer → extractor → gateway → provider`；`eval/` 只读消费；`llm/` 不知道抽取 Schema。

## 6. CLI 命令速查

| 命令 | 用途 |
|---|---|
| `db-upgrade` / `seed` | 迁移 + 初始化（幂等） |
| `collect --file jd.txt` | **日常收集**：从文件读 JD → 自动识别字段 → 回车确认 → 追加批次 CSV |
| `collect --drop-last` | 录错重录：删批次 CSV 最后一条 |
| `import --file data/batch_1.csv` | 批次 CSV 导入入库（批次报告 + ingest_batch 历史） |
| `ingest-adzuna` | 海外拉取（默认 gb，配额守卫 250 req/day） |
| `contribute` / `delete-contribution` | 匿名贡献通道（opt-in + PII + deletion_code） |
| `stats --market china [--category --city --salary-min/max --window-start/end --min-sample]` | 频率统计（S11 口径，支持 4 维切片） |
| `snapshot-create --market china` | 生成市场统计快照（append-only，N<30 拒写；已产出 snapshot#1） |
| `skill-evidence --skill RAG --market china` | 技能 → 支撑 JD 溯源底账（含 evidence_text 回原文） |
| `market-crosscheck --market china` | 与 MARKET_RESEARCH §2.1 方向一致性对照（tau + 逐技能 diff） |
| `quality-report` | E5 数据质量 JSON 报告 |
| `jd-analyze --file jd.txt --title t` | 粘贴 JD → 结构化分析（M1，不落库，需 key） |
| `eval-e1` | E1 抽取评测跑分（需 key） |
| `backfill-extraction` | 回填 pending 抽取（需 key） |
| `quarantine-list` / `raw-cleanup` | 隔离队列 / 7 天 raw 清理 |

## 7. 当前核心工作流：人工 JD 收集（Phase 2 遗留）

目标：中国市场 **200-300 条**，分 4-5 批，每批 50 条后校准词表。**批次 1 已完成**（50 条已导入）。

日常操作（绝对路径锁定版，任意目录可跑）：

```powershell
# 1. 把新 JD 粘贴进 jd.txt，然后：
cd "E:\codexproject\SkillGap Agent"; & "E:\codexproject\SkillGap Agent\.venv\Scripts\skillgap.exe" collect --file "E:\codexproject\SkillGap Agent\jd.txt" --out "E:\codexproject\SkillGap Agent\data\batch_1.csv"
# 2. 收集满一批后导入：
& .venv\Scripts\skillgap.exe import --file "E:\codexproject\SkillGap Agent\data\batch_1.csv"
```

收集器自动完成：标题/公司/城市抽取、薪资识别（防日期误判）、岗位类别归类（自由文本自动回退枚举）、must_have/nice_to_have 自动建议（"加分项"/"了解"→nice_to_have，"至少一门/或"→nice_to_have）、技能建议（词表 alias 扫描）、PII 脱敏、CSV 中文表头 + 自动转义（Excel 兼容 BOM）。

**收集来源纪律**（ADR-002 / DATA_GOVERNANCE）：不爬虫（ADR-001），公司页面人工摘录必须带 source_url；每批导入后跑 `quality-report` 核对。

## 8. 数据库现状（2026-09-02）

- **50 条岗位**（批次 1，全部 `public_job_page` / market=china；2 条 example.com 测试遗留已删除）
- 类别分布：agent_dev 20 / ai_application_dev 16 / llm_fullstack 10 / ai_platform 4
- **408 行 job_skill**（manual 标注），无未解析候选
- 批次 1 抽样核对（21 条）已完成：修复"从 0 到 1"薪资误判 bug（job 53/72/99，commit 30a7370），其余字段与原文一致；抽查底账 `data/verify_batch1_sample20.csv`
- 词表 v1.5：79 技能（2026-09-02 增补算法/测试类 7 项：机器学习/深度学习/NLP/软件测试/自动化测试/接口测试/性能测试）；来源注册表 5 条（adzuna / company_career_page / user_contribution / community_csv / demo_dataset）
- E1 标注集：20 条种子（`data/eval/e1_seed_v1.json`）
- **market_snapshot：snapshot#1**（2026-09-02，N=50，medium，s11-v1；top：Python 0.76 / Java 0.58 / RAG 0.54；与 MARKET_RESEARCH §2.1 交叉对照 tau=0.1538——首跑记录 `docs/plans/phase4_first_run_results.md`）

## 9. 遗留任务（按优先级）

1. **继续收集批次 2-4**（每批 50 条，采集→导入→`quality-report` 核对→校准词表→`snapshot-create` 更新快照）
2. ~~配置 LLM_API_KEY 跑 E1 真实基线~~ ✅ 已完成（2026-09-02，deepseek-chat，eval_run#2：**F1=0.914 / P=0.9659 / R=0.8673 / evidence_rate=1.0 / importance_accuracy=0.8706，verdict=PASS**，远超 0.75 warn 线；eval_run 历史含 #1 block——key 粘贴重复导致的 401 诚实留档。后续：标注集 v2 扩至 50-100 条后重跑回归）
3. ~~抽样 20 条人工核对字段~~ ✅ 已完成（2026-09-02，21 条分层抽查；发现并修复薪资"从 0 到 1"误判 bug，详见 §8）
4. **标注集 v1 → v2**：从首批真实 JD 扩展至 50-100 条（不静默改 v1）
5. **Adzuna 首批拉取**（额度节奏 250 req/day，market=global 无污染验证；global 快照通道已就绪）
6. ~~进入 Phase 4~~ ✅ 已完成（2026-09-02，PHASE_4_REVIEW.md；下一步 Phase 5 Candidate Profile——先写 docs/plans/ 计划）

## 10. 已知问题与坑

| 问题 | 处置 |
|---|---|
| **pytest 默认临时目录权限被拒**（`C:\Users\...\Temp\pytest-of-ASUS`，WinError 5） | 跑测试必须加 `--basetemp` 指向项目内目录 |
| PowerShell 不支持 bash heredoc | git commit 多行信息用单行 `-m` 或写临时文件 |
| 终端直接粘贴长 JD 会被截断 | 一律走 `collect --file jd.txt` 通道（已解决） |
| Excel 打开 CSV 乱码 | 模板带 UTF-8 BOM（`utf-8-sig`），勿用记事本另存为 ANSI |
| README.md 只有标题 | Phase 11 统一补（不提前写营销文档） |

## 11. 纪律约束（必须遵守）

1. **Git：仅本地提交，禁止 push 远程**（历史决议：远程 phase3 tag 已删、远程 master 已删）。当前本地 master 领先 origin/main 26+ commits，属预期状态。
2. 范围变更先改 `MVP.md`/ADR 再动代码；新增依赖先补 ADR。
3. 禁止跳过测试进入下一阶段；禁止一次生成多阶段代码（Plan → Implement → Test → Review 节奏）。
4. Prompt 任何变更必须跑 `eval-e1` 回归（F1 历史可比）。
5. 中文 JD 无合法自动化数据源——项目不建立在反爬对抗上（ADR-001，手动粘贴优先）。

## 12. 关键文档索引

| 文档 | 内容 |
|---|---|
| `docs/ROADMAP.md` | 阶段总览 + 各 Phase 规格 + 自检记录（**先读这个**） |
| `docs/MVP.md` | MoSCoW 范围冻结 + 质量门禁 G1-G6 |
| `docs/DATA_PIPELINE.md` | S1-S12 管道分步规格 |
| `docs/DATA_MODEL.md` | 21 张表 + 字段口径（§5.1 类别规则、§7 列规格） |
| `docs/DATA_GOVERNANCE.md` | PII/保留期/API 条款核查 |
| `docs/DATA_COLLECTION.md` | 人工收集规范与批次协议 |
| `docs/API.md` | 16 端点契约（§2.1 jd-analyze 结构） |
| `docs/EVALUATION_PLAN.md` | E1-E5 指标与阈值（§7 失败分诊） |
| `docs/adr/ADR-001~010` | 全部架构决策（Context/Options/Decision） |
| `PHASE_1/2/3_REVIEW.md` | 各阶段验收与六维自检 |
| `docs/plans/` | Phase 2/3 实施计划（Phase 4 计划待写） |

个人学习文档（面试题库/知识缺口/学习路线/简历映射）：根目录 `docs/INTERVIEW_QUESTION_BANK.md`、`KNOWLEDGE_GAPS.md`、`LEARNING_ROADMAP.md`、`PROJECT_LEARNING_GUIDE.md`、`PROJECT_TECH_MAP.md`、`RESUME_TECH_MAPPING.md`（均为未跟踪文件，未入库）。
