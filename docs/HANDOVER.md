# SkillGap Agent —— 项目交接文档

> 更新：2026-10-03（Phase 11 收口 + CI 首跑闭环同步）｜ 代码状态：master 已与远端同步（Phase 11 收官，run 37092541082 三 job 全绿）｜ 测试：540 passed
> **换账号 / 换机交接：先读 §13 迁移清单**

## 1. 项目一句话

**SkillGap Agent**（原暂定名 JobLens）：证据化技能决策系统——不是简历匹配工具。核心链路：收集中文 AI 岗位 JD → 技能抽取（带原文证据）→ 市场统计 → 候选人画像 → Skill Gap 量化 → 可解释匹配 → ROI 学习建议。

差异化四支柱：自建数据集 + 证据化画像 + ROI 优先级 + 三层评测。定位与决策依据见 `docs/PRODUCT_SPEC.md`、`docs/ROADMAP.md`。

## 2. 当前进度

```
Phase 0  市场与竞品研究          ✅ 完成（10 份研究文档）
Phase 1  需求冻结 + 架构设计      ✅ 完成（ADR-001~010，16 端点契约）
Phase 2  数据模型 + 管道 + 数据集 ✅ 代码完成；数据收集 N=201（high，批次 1-3 已入库）
Phase 3  JD Analyzer + LLM 抽取  ✅ 完成（E1 基线 2026-09-02：F1=0.914 PASS，eval_run#2）
Phase 4  Market Intelligence     ✅ 完成（2026-09-02；snapshot#4 N=201 high，tau=0.1538）
Phase 5  Candidate Profile          ✅ 完成（2026-09-03；conf-v1 公式冻结，画像 A/B/C 固定）
Phase 6  Skill Gap                 ✅ 完成（2026-09-03；gap-v1 冻结：纯星级差 + genuine/transferable + 类目聚合）
Phase 7  Job Matching              ✅ 完成（2026-09-03；scoring 1.0.0 + E2 基线 PASS：ρ=0.8433/MAE=9.38/对抗三用例全过）
Phase 8  Recommendation           ✅ 完成（2026-09-04；roi-v1 + LangGraph Agent + E3 基线 PASS：nDCG@5=0.6497；首个新依赖 langgraph 0.3.34）
Phase 9  Evaluation 汇总          ✅ 完成（2026-09-08；eval-gate 门禁 + eval-report 报告 + CI 首个 workflow + E1 方差演练 PASS；443 测试）
Phase 10 Dashboard                ✅ 完成（2026-09-16；FastAPI 10 契约端点 + Jinja2 SSR 六页 + 原生 JS；真实 LLM 全流程走查七步全通；505 测试）
Phase 11 Docker + CI + 文档       ✅ 完成（2026-09-24；compose 全栈（ADR-012）+ C1 延后五端点收口（16 端点=14 HTTP+2 CLI）+ Data & Quality 页七页导航 + README/DATA/DEVELOPMENT/DEMO 终版 + 全新环境三命令自演示走查；540 测试。**MVP（M1-M11）至此全部达成**）
```

阶段验收记录：根目录 `PHASE_1_REVIEW.md` ~ `PHASE_11_REVIEW.md`（每阶段一份：六维自检 + 验收核验表）。

## 3. 技术栈与架构

| 层 | 选型 | 说明 |
|---|---|---|
| 语言 | Python 3.12+（项目 `.venv`） | 入口 `skillgap` CLI（pyproject scripts） |
| 数据库 | PostgreSQL 16 + pgvector（Docker） | `pgvector/pgvector:pg16`；pgvector 索引延后（ADR-004"Phase 8 才建"≠"必须建"——精确溯源已由 skill-evidence SQL 覆盖，语义检索未达触发线，见 D-2026-09-04-15） |
| LLM | DeepSeek（deepseek-chat） | OpenAI-compatible 直连 httpx，**不用 openai SDK**（用户决策 Q4） |
| Agent 编排 | langgraph 0.3.34（锁 ≥0.3,<0.4） | Phase 8 引入（ADR-006 复议）：单 Career Planner Agent，4 节点图，解释层旁路——数值路径零 LLM 权限 |
| 测试 | pytest（需真实 PostgreSQL 跑 `skillgap_test` 库） | 540 项，全部本地可跑（本机必须 `--basetemp`，见 §4/§10） |
| 部署 | Docker Compose 全栈（ADR-012，Phase 11） | postgres + app（entrypoint 幂等 migrate→seed→serve）+ redis；端口 `127.0.0.1:8000` 红线延续 |

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
  extract/             # Phase 3 LLM 抽取
    prompt.py         #   PROMPT_VERSION=v2（变更须跑 eval-e1 回归）
    llm_extractor.py  #   Structured Output + 证据定位校验 + 对话式重试
    analyzer.py       #   analyze_jd()：确定性字段 + LLM 抽取；backfill 兜底零词表标注
  llm/                #   provider.py（httpx 重试）/ gateway.py（DB 缓存）
  eval/               #   e1.py（P/R/F1 + 阈值 + eval_run 历史）/ seed.py（v1+v2 双版本）
  taxonomy/           #   词表 v1.9（87 技能 + alias）+ skill_relations
  profile/            # Phase 5 Candidate Profile
    confidence.py     #   纯函数 conf-v1（零 LLM 依赖，守卫测试锁定）
    prompt.py         #   RESUME_PROMPT_VERSION=v1（证据分级 + level 程度词映射）
    extractor.py      #   LLMResumeExtractor（复用 gateway + 证据定位校验）
    service.py        #   analyze_resume/get_profile/add_manual_skill/delete_candidate
                      #   权重规则表 docs/WEIGHT_RULES.md（公开）
  gap/                # Phase 6 Skill Gap（零 LLM）
    gapcalc.py        #   纯函数 gap-v1（required_level 映射/gap clamp/classify，守卫测试锁定）
    service.py        #   get_gaps：单岗(job_id)/类目聚合(category)双模式
                      #   口径裁决与聚合规则 DECISION_LOG D-2026-09-03-13
  match/              # Phase 7 Job Matching（零 LLM）
    scoring.py        #   compute_match 纯函数（scoring 1.0.0 四维加权，守卫测试锁定）
    service.py        #   match_score（job_id 模式）+ match_score_text（jd_text 无状态模式 C4，不落库）
    explanation.py    #   确定性模板解释（数字 100% 来自 breakdown；LLM 解释数字经程序比对）
  stats.py            #   Phase 4 市场统计：切片频率/快照/溯源/交叉对照（零 LLM，守卫测试锁定）
                      #   口径文档 docs/STATS_METHOD.md；method_version=s11-v1
  recommend/          # Phase 8 Recommendation
    roi.py           #   纯函数 roi-v1（Demand×Gap÷Cost，零 LLM/零 import，守卫测试锁定）
    service.py       #   recommend：market 聚合 + snapshot demand + 模板匹配 + 落库（ADR-008 守门）
    agent.py         #   LangGraph Career Planner（load→generate→verify→revise/降级，数值零污染）
  retrieval/          # Phase 8 RAG 引用层
    service.py        #   embedding 回填（bge-m3 1024 维）+ 语义检索 → (job, skill, evidence) 溯源
  eval/               #   e1.py / e2.py / e3.py（三评测器，eval_run 历史连续）+ seed.py
  quality_metrics.py  #   E5 数据质量报告
  api/                # Phase 10/11 FastAPI + Dashboard（ADR-011）
    app.py            #   create_app 工厂（统一错误体三 handler + /static 挂载 + 路由装配）
    deps.py           #   get_conn 每请求连接（无池；compose 复议已关闭——维持无池 D-2026-09-18-19）
    errors.py         #   ApiError 独立模块（防循环导入）
    routes_*.py       #   14 HTTP 契约端点（jd/match/recommend/profile/market/contribute/quality）+ routes_web.py SSR 七页
    templates/        #   Jinja2 八模板（base + dashboard/resume/jd/match/recommend/market/quality）
    static/           #   app.js + style.css（零框架零构建零 CDN；localStorage 会话 C6）
migrations/           # 001 init / 002 batch error_count / 003 llm_cache+eval_run / 004 rag_evidence / 005 task
docs/                 # 全部设计文档 + adr/（12 份 ADR）+ plans/
tests/                # 52 个测试文件（另 1 份仅本地），conftest 起真实 PG 测试库
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
| `snapshot-create --market china` | 生成市场统计快照（append-only，N<30 拒写；已产出 snapshot#4） |
| `skill-evidence --skill RAG --market china` | 技能 → 支撑 JD 溯源底账（含 evidence_text 回原文） |
| `market-crosscheck --market china` | 与 MARKET_RESEARCH §2.1 方向一致性对照（tau + 逐技能 diff） |
| `quality-report` | E5 数据质量 JSON 报告 |
| `jd-analyze --file jd.txt --title t` | 粘贴 JD → 结构化分析（M1，不落库，需 key） |
| `eval-e1` | E1 抽取评测跑分（需 key） |
| `backfill-extraction` | 回填 pending / 零词表标注抽取（需 key） |
| `resume-analyze --file resume.txt [--candidate-id N]` | 简历纯文本 → 证据化画像（M5，需 key；重分析=替换式，manual 行保留） |
| `profile-get --candidate-id N` | 画像查询（每技能证据链 + confidence） |
| `profile-add-skill --candidate-id N --skill X --level 4 [--evidence "…"]` | 手动勾选技能（manual 证据，confidence=1.0，词表内） |
| `candidate-delete --candidate-id N` | 级联删除画像（204/404） |
| `gap-get --candidate-id N --job-id M` 或 `--category c [--market china --min-freq 0.2]` | 岗位要求 vs 画像差距量化（M7，零 LLM：gaps+transferable+demand/cost 原料） |
| `recommend --candidate-id N [--budget 14] [--market china] [--templates P]` | ROI 优先级建议（M9，零 LLM：Top-10 排序 + 模板项目匹配 + recommendation 落库） |
| `agent-plan --candidate-id N [--budget 14]` | Career Planner 叙事（LangGraph，需 key；数字一致性校验 + 失败降级模板） |
| `serve [--host] [--port]` | Dashboard/API 服务（Phase 10；默认 127.0.0.1:8000 仅本机——API.md §0 部署红线，对外须显式传参） |
| `eval-e3 [--dataset P] [--seed-only] [--judge]` | E3 推荐评测跑分（指标零 LLM 无 key 可跑；标注集自动入库；--judge 附 deepseek-reasoner 评分，Warn 级不参与 verdict） |
| `rag-index [--batch-size N]` | RAG 引用层：回填 job_skill 证据行 embedding（bge-m3 1024 维，幂等；需 EMBEDDING_API_KEY） |
| `rag-search --query Q [--market M] [--top-k K]` | RAG 语义检索：查询 → (job, skill, evidence_text) 溯源（"模型上下文协议"→MCP 类语义变体；先 rag-index） |
| `quarantine-list` / `raw-cleanup` | 隔离队列 / 7 天 raw 清理 |

## 7. 当前核心工作流：JD 收集（Phase 2 遗留）

目标：中国市场 **200-300 条**，分批推进，每批导入后校准词表。**批次 1-3 已完成（N=201，confidence=high）**——收集目标已达成，后续按需小幅补充（词表扩容后可采新方向验证）。

日常操作（绝对路径锁定版，任意目录可跑）：

```powershell
# 1. 把新 JD 粘贴进 jd.txt，然后：
cd "E:\codexproject\SkillGap Agent"; & "E:\codexproject\SkillGap Agent\.venv\Scripts\skillgap.exe" collect --file "E:\codexproject\SkillGap Agent\jd.txt" --out "E:\codexproject\SkillGap Agent\data\batch_1.csv"
# 2. 收集满一批后导入：
& .venv\Scripts\skillgap.exe import --file "E:\codexproject\SkillGap Agent\data\batch_1.csv"
```

收集器自动完成：标题/公司/城市抽取、薪资识别（防日期误判）、岗位类别归类（自由文本自动回退枚举）、must_have/nice_to_have 自动建议（"加分项"/"了解"→nice_to_have，"至少一门/或"→nice_to_have）、技能建议（词表 alias 扫描）、PII 脱敏、CSV 中文表头 + 自动转义（Excel 兼容 BOM）。

**收集来源纪律**（ADR-002 / DATA_GOVERNANCE）：公司页面人工摘录必须带 source_url；每批导入后跑 `quality-report` 核对。

## 8. 数据库现状（2026-09-24；权威口径见 docs/DATA.md §2）

- **202 条 active 岗位**（全 china = 201 条批次导入 + 1 条 E2 评测物化 e90c76b；2026-09-22 卷事故重建后现状，批次历史与事故全记录见 DATA.md §2/§6。原批次构成：批次 1：50 条 company_career_page；批次 2：50 条 = 手动 23 + boss_zhipin 27；批次 3：101 条 boss_zhipin——主流方向补采：Agent 全栈/AI 应用开发/大模型算法/RAG/推理优化/多模态/NLP/Golang AI，覆盖北上深杭广蓉宁汉长 9 城）
- 批次 3 数据清洗：删除 7 条非技术岗混入（城市合伙人/设计/运营/销售/内容生产岗）；质检词表补"评测"信号（救回模型评测岗误杀）；时薪/日薪按 174h / 21.75 天折算月薪入库
- **1518 行 job_skill**（含 RAG 向量 1512）；quality-report missing_field_rate=0
- 批次 1 抽样核对（21 条）已完成：修复"从 0 到 1"薪资误判 bug（job 53/72/99，commit 30a7370），其余字段与原文一致；抽查底账 `data/verify_batch1_sample20.csv`
- 词表 v1.9：87 技能（2026-09-02 增补算法/测试/系统架构/前端 + Context Engineering + Harness Engineering；**候选裁决**：新增 Agent 开发/小程序 2 技能 + AI Coding(claude code/codex/claude)、LLM 应用开发(大模型API)、前端开发(前端) 别名扩充，11 accepted / 25 rejected，队列清零）；来源注册表 6 条（adzuna / company_career_page / boss_zhipin / user_contribution / community_csv / demo_dataset）
- E1 标注集：v1（20 条合成变体，冻结）+ **v2（53 条真实 JD**：28 条人工确认行直取库内标注 + 25 条平台采集行逐条复核重标——修正规则误标：react 模式≠前端 React、GitHub Copilot≠Git、任一/均可≠must、补 Claude Code→AI Coding；`data/eval/e1_seed_v2.json`）
- **market_snapshot：snapshot#1（重建）**（2026-09-22，N=202，**high**，s11-v1——事故后重建；事故前快照历史 #1 N=50 → #2 N=100 → #3 N=193 → #4 N=201 随卷丢失，数值存档于 DATA.md 与 DECISION_LOG D-2026-09-22-20）
- 走查留痕（2026-09-22 事故恢复重建）：candidate cid=1 画像（9 技能）——开发验证数据，可随时 `candidate-delete --candidate-id 1` 级联清除（Phase 10 走查原为 cid=9，随数据卷事故丢失后重建，见 DECISION_LOG D-2026-09-22-20）

## 9. 遗留任务（按优先级）

1. ~~继续收集批次 3~~ ✅ 已完成（2026-09-02，批次 3 共 101 条入库，N=201 达 high；含 E1 v2 基线首跑：F1=0.8669 / P=0.9433 / R=0.802 / **evidence_rate=1.0** / importance_accuracy=0.6804，verdict=warn——prompt v2 跨行证据修复完全验证，recall 与 importance 为后续迭代方向）
2. ~~配置 LLM_API_KEY 跑 E1 真实基线~~ ✅ 已完成（2026-09-02，deepseek-chat，eval_run#2：**F1=0.914 / P=0.9659 / R=0.8673 / evidence_rate=1.0 / importance_accuracy=0.8706，verdict=PASS**，远超 0.75 warn 线；eval_run 历史含 #1 block——key 粘贴重复导致的 401 诚实留档）
3. ~~抽样 20 条人工核对字段~~ ✅ 已完成（2026-09-01，21 条分层抽查；发现并修复薪资"从 0 到 1"误判 bug，详见 §8）
4. ~~标注集 v1 → v2~~ ✅ 已完成（2026-09-02，53 条真实 JD。**评测闭环捕获并修复真实 prompt 缺陷**：v2 数据集暴露 v1 prompt 在项目符排版 JD 上产生跨行证据 → prompt v2 增补"证据不得跨越列表符号/换行"。当前基线（eval_run#4/#5，prompt v2）：v2 数据集 warn（F1=0.8669 / R=0.802 / evidence=1.0，真实 JD 难于合成）；v1 数据集 pass（F1=0.9043）无回归。recall 0.802 距 0.85 pass 线的差距主要是 must/nice 边界与"任一"型列举的标注粒度分歧——后续 prompt 迭代方向，禁止为跑分过拟合评测集）
5. **Adzuna 首批拉取**（额度节奏 250 req/day，market=global 无污染验证；global 快照通道已就绪）
6. ~~进入 Phase 5~~ ✅ 已完成（2026-09-03，PHASE_5_REVIEW.md；conf-v1 公式 + 3 冻结画像 + CLI 4 命令，242 测试全绿。**已知限制**：LLM level 推断无评测集背书（E2 属 Phase 7），手动勾选兜底；简历输入为纯文本，PDF 后置）
7. ~~进入 Phase 6~~ ✅ 已完成（2026-09-03，PHASE_6_REVIEW.md；gap-v1 冻结 + CLI gap-get，277 测试全绿。**口径裁决**：confidence 不进 gap（C1）/ 类目聚合规则冻结（C2）——DECISION_LOG D-2026-09-03-13。下一步 Phase 7 Job Matching——先写 docs/plans/ 计划；E2 标注集（20-30 对）是该阶段重点前置）
8. ~~进入 Phase 8~~ ✅ 已完成（2026-09-04，PHASE_8_REVIEW.md；roi-v1 + LangGraph Agent + E3 基线 pass（nDCG@5=0.6497），410 测试全绿。**judge 已补做**：rubric-v1 真实基线 mean=5.0（eval_run #9，Warn 级不参与 verdict）。**RAG 引用层已激活**：1514 行证据已回填（bge-m3），跨语言/语义变体检索验证过（D-2026-09-04-16 激活记录）。待办：E3 标注双人复核（user 复核 + 同学抽标）。已知偏差（"Python 补到精通"/新手画像成本项冲突）为 v2 校准候选，见 data/eval/e3_report_v1.json）
9. ~~进入 Phase 9~~ ✅ 已完成（2026-09-08，PHASE_9_REVIEW.md；gate 汇总门禁 + eval-report 报告 + CI 首个 workflow + 零漂移/taxonomy/劣化演练测试锚定 + E1 方差演练 PASS（极差 0.0145<0.03），443 测试全绿。docs/EVALUATION.md 为评测 README。**开放项**：CI 首跑绿待 push（workflow 须在远端生效）；E3 标注双人复核（user + 同学）仍待办。**遗留观察**：E1 verdict 对 LLM 服务可用性敏感——evidence_rate<1.0 一票 block 会被 DeepSeek 瞬时失败触发（T6 真实案例：#10-12 block → #14 恢复 warn），分诊处置见 EVALUATION.md §9）
10. ~~进入 Phase 10~~ ✅ 已完成（2026-09-16，PHASE_10_REVIEW.md；FastAPI 10 端点 + Jinja2 SSR 六页 + 原生 JS 前端，505 测试全绿。**走查**：真实 LLM 全流程七步全通，捕获并修复 7 真实缺陷（含 dependency_overrides 测试盲区——结构级回归测试固化）。**远端进度**：master 已推至 Phase 8（665d0db），Phase 9/10 本地待审批推送；CI 首跑绿仍待 push。**Phase 11 输入**：C1 延后端点清单（contribute/import/adzuna/tasks/quality/eval）+ Data & Quality 页 + compose 连接池复议（D1）。下一步 Phase 11 Docker + CI + Documentation——先写 docs/plans/ 计划）
11. ~~进入 Phase 11~~ ✅ 已完成（2026-09-24，PHASE_11_REVIEW.md；compose 全栈（Dockerfile+entrypoint 幂等+ADR-012）+ C1 延后五端点（contribute/tasks/quality/eval/deletion——16 端点=14 HTTP+2 CLI）+ Data & Quality 页（导航七页）+ CI docker build job + README 七段/DATA.md/DEVELOPMENT.md/DEMO.md 文档终版（零偏差抽查 12 项）+ 全新环境三命令自演示走查（两真实缺陷当次修复），540 测试全绿。**MVP（M1-M11）至此全部达成**。开放项：①~~Phase 10/11 待 push~~ ✅ 已闭环（2026-10-03 十九笔全量 push，CI 首跑三 job 全绿 run 37092541082 @753abd7——pytest 58s / docker build 25s 远端首次执行 / e1 skipped 正常）②~~E1 dispatch 待 secret~~ ✅ 已闭环（2026-10-03：`LLM_API_KEY` secret 经 API 配置 + dispatch 首跑 run 37093065875 三 job 全绿——E1 v2 f1=0.8710 warn / v1 f1=0.8962 warn，failures 0，一次性库数字以 CI 日志为准）③~~E3 标注双人复核~~ ✅ 已闭环（2026-10-03，D-2026-10-03-21：AI 跨模型交叉复核 GLM-5.3 报告 `data/eval/e3_review_v1.json`——35 条 31 全同意+4 带判断标记+0 分歧、频次声明 2/2 实证属实、不改标注值基线无需重跑；user 终审 F1/F2/F3 裁决保留原标，35 条全部确认；同学抽标降级可选）④Adzuna 首批拉取 ⑤自演示录制（用户侧，DEMO.md 已入库）；另：GitHub 默认分支已切 master + main 已快进对齐（2026-10-03）

## 10. 已知问题与坑

| 问题 | 处置 |
|---|---|
| **pytest 默认临时目录权限被拒**（`C:\Users\...\Temp\pytest-of-ASUS`，WinError 5） | 跑测试必须加 `--basetemp` 指向项目内目录 |
| PowerShell 不支持 bash heredoc | git commit 多行信息用单行 `-m` 或写临时文件 |
| 终端直接粘贴长 JD 会被截断 | 一律走 `collect --file jd.txt` 通道（已解决） |
| Excel 打开 CSV 乱码 | 模板带 UTF-8 BOM（`utf-8-sig`），勿用记事本另存为 ANSI |
| ~~README.md 只有标题~~ | ✅ Phase 11 T7 已重写为七段终版（Problem/Solution/Architecture/Demo/Evaluation/Limitations/Roadmap，红线技术向非营销） |

## 11. 纪律约束（必须遵守）

1. **Git：master 与 phase 标签推送 GitHub**（2026-09-02 起解除"仅本地"约束；`tests/test_prompt.py` 保持仅本地不跟踪）。注意 docs 中不得记录数据采集工具的逆向相关细节。
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
| `docs/API.md` | 16 端点契约（14 HTTP 实现 + 2 CLI 通道；§2.1 jd-analyze 结构） |
| `docs/EVALUATION_PLAN.md` | E1-E5 指标与阈值（§7 失败分诊） |
| `docs/EVALUATION.md` | 评测 README（冻结宣告/基线/方差/演练/分诊，**面试三问之"怎么证明有效"**） |
| `docs/DATA.md` | 数据现状权威口径（三通道×Tier/库快照/批次历史/统计口径/事故全记录，**面试三问之"数据从哪来"**） |
| `docs/DEVELOPMENT.md` | 开发环境/测试/CI/迁移指南（Windows 坑表含 down -v 事故教训） |
| `docs/DEMO.md` | 全新环境自演示脚本（三条命令 + 浏览器七页全流程 + 常见问题） |
| `docs/adr/ADR-001~012` | 全部架构决策（Context/Options/Decision；ADR-011 = FastAPI 引入；ADR-012 = Docker 部署容器化） |
| `PHASE_1~11_REVIEW.md` | 各阶段验收与六维自检 |
| `docs/plans/` | Phase 2-11 实施计划（各含口径裁决 C* 与冻结决策 D*） |

个人学习文档（面试题库/知识缺口/学习路线/简历映射）：根目录 `docs/INTERVIEW_QUESTION_BANK.md`、`KNOWLEDGE_GAPS.md`、`LEARNING_ROADMAP.md`、`PROJECT_LEARNING_GUIDE.md`、`PROJECT_TECH_MAP.md`、`RESUME_TECH_MAPPING.md`（均为未跟踪文件，未入库）。

## 13. 账号切换与环境迁移清单（2026-10-03 更新）

> 换账号（GitHub / IDE·AI 助手）或换机前逐项核对。两类场景影响面不同：**同机换账号**——磁盘文件、git 仓库、Docker 数据库全部保留，受影响的只有账号凭证与 AI 会话上下文；**换机 / 重新克隆**——下表"仅本地"文件一律不随 git 走，必须单独带走。

### 13.1 Git 与远端（换 GitHub 账号必读）

- 远端：`origin = https://github.com/Xhan-985/SkillGap-Agent.git`，`origin/master` 与本地 master **已同步**（Phase 11 收官 753abd7 + CI 闭环补注；2026-10-03 push 后 CI 首跑三 job 全绿 run 37092541082——pytest 58s / docker build 25s 远端首次执行 / e1 skipped 正常）
- 推送纪律：push 需用户明确批准；本地代理 127.0.0.1:7890（git http.proxy 已配）；代理不可用时直连单次覆盖：`git -c http.proxy= -c https.proxy= push origin master`
- 换账号后动作：`git remote set-url origin <新仓库地址>`；新仓库 GitHub Secrets 重配 `LLM_API_KEY`（E1 dispatch workflow 依赖）；推送后看 Actions 页确认三 job 绿（历史 run 见上）

### 13.2 仅本地文件（git 不跟踪——换机/重新克隆会丢）

| 文件/目录 | 内容 | 换机动作 |
|---|---|---|
| `.env` | 全部密钥：`DATABASE_URL` / `TEST_DATABASE_URL` / `LLM_API_KEY`（DeepSeek）/ `ADZUNA_APP_ID`+`ADZUNA_APP_KEY` / `EMBEDDING_API_KEY` | **必须手动带走**（或按 `.env.example` 重填） |
| `tests/test_prompt.py` | 本地提示词实验（纪律：仅本地不入库） | 按需 |
| `jd.txt`、`data/resume_sample.txt` | 个人数据（纪律：不入库） | 手动带走 |
| 走查截图 / 自演示录制产物 | Phase 10/11 走查截图与录屏（C5 裁决：脚本入库、产物不入库） | 按需带走 |
| `docs/` 下 6 份个人学习文档 | 面试题库/知识缺口/学习路线/技术映射等（清单见 §12 末行） | 手动带走 |
| `.boss/`、`.boss-data/`、`scripts/` | 本地工具与调试目录（.gitignore 约定不入库） | 按需 |
| `.venv/` | Python 环境 | 不迁移，新机 `pip install -e ".[dev]"` 重建 |

### 13.3 数据库（同机换账号不受影响；换机必读）

- 数据在 Docker PostgreSQL（`pgvector/pgvector:pg16`）中，**不在 git**（2026-09-22 事故重建后现状，明细见 docs/DATA.md §2）：202 条 active 岗位 + 1518 行 job_skill（RAG 向量 1512）+ 词表 v1.9（87 技能 + 288 别名）+ 来源注册表 + market_snapshot#1（重建）+ eval_run 4 条（重建）+ 走查留痕（candidate cid=1 等）
- 换机重建路径（Phase 11 起最简：`docker compose up -d` 一条命令全栈，entrypoint 自动 db-upgrade+seed，见 DEMO.md；分步版）：`db-upgrade` + `seed`（词表/来源表可重建）→ 逐批 `import data/batch_1~3.csv`（岗位可重建，批次 CSV 已入库跟踪）→ `snapshot-create`（快照可重算）→ `rag-index`（向量可重灌，需 EMBEDDING_API_KEY）
- **不可自动重建**：eval_run 历史行与画像/匹配留痕（2026-09-22 事故实证：14 条历史丢失，E1/E2/E3 重跑可回基线带内但历史轨迹仅存档于 data/eval/*.json 与 EVALUATION.md）→ 建议换机前 `pg_dump` 整库带走最稳妥

### 13.4 AI 会话上下文（换 IDE / AI 助手账号）

- AI 助手的项目记忆与历史会话**不保证随账号迁移——按不迁移做最坏打算**：新账号首个会话没有任何历史上下文
- 恢复路径（新会话按序阅读即可接续）：本文档 → `docs/ROADMAP.md`（阶段总览与状态行）→ `PHASE_11_REVIEW.md`（最近阶段验收 + 口径裁决核对）→ `docs/plans/`（各阶段实施计划，含口径裁决 C* 与冻结决策 D*）
- 工作纪律速查：§11（git/范围/测试/prompt 纪律）+ §4（测试必须 `--basetemp` + `.venv\Scripts\python.exe`，系统 Python 无 pytest）+ §10（本机已知坑）

### 13.5 迁移后自验（三步确认环境完好）

```powershell
# 前置：Docker Desktop 手动启动；.venv 重建（pip install -e ".[dev]"）；.env 就位
# 最简（Phase 11 推荐，一条命令全栈，见 docs/DEMO.md）：
docker compose up -d    # entrypoint 自动 db-upgrade + seed + serve，http://127.0.0.1:8000
# 分步等价版：
docker compose up -d postgres
& .venv\Scripts\skillgap.exe db-upgrade
& .venv\Scripts\skillgap.exe seed
& .venv\Scripts\python.exe -m pytest tests/ -q --basetemp=".pytest_tmp"   # 期望 540 passed, 0 skipped
& .venv\Scripts\skillgap.exe serve                                        # http://127.0.0.1:8000 浏览器七页走一遍
```
