# Phase 11 Review —— Docker + CI + Documentation 验收与六维自检

> 阶段：Docker 全栈 compose 化 + CI docker build job + 文档终版（README/DATA/DEVELOPMENT/DEMO）+ C1 延后端点收口 + Data & Quality 页 + 全新环境自演示。
> 计划：`docs/plans/2026-09-18-phase11-docker-ci-docs.md`（口径裁决 C1-C7 + 冻结决策 D1-D10）。

## 0. 交付物清单

| # | 交付 | 位置 | commit |
|---|---|---|---|
| T1 | 计划落档 + ADR-012（Docker 部署容器化）+ DECISION_LOG D-2026-09-18-19（C1-C7 裁决 + D1-D10 冻结 + Phase 10 D1 连接池复议关闭——维持无池） | `docs/plans/` + `docs/adr/` + `docs/DECISION_LOG.md` | 4fd5583 |
| T2 | Dockerfile（python:3.12-slim 单阶段 + 非 root + editable 安装——MIGRATIONS_DIR 源码树相对定位）+ entrypoint.sh 三步幂等（db-upgrade→seed→serve）+ compose app service（environment 注入服务名连接串，用户 .env 零改动） | `Dockerfile` + `docker/entrypoint.sh` + `docker-compose.yml` + `.gitattributes`/`.dockerignore` | 3d5ab98 |
| T3 | 同步收尾端点：quality/report（五指标+批次聚合）+ eval/results（版本三元组+差异摘要）+ DELETE contributions（§2.14 哈希比对 204/404 防探测字节级一致） | `api/routes_quality.py` + `api/routes_contribute.py` + 9 测试 + 真实库 curl 验证 | 9f0b0f8 |
| T4 | 任务基础设施 + contribute：migration 005 task 表 + POST /api/jd/contribute（202+BackgroundTasks）+ GET /api/tasks/{id}（D5 一次性 code）+ run_contribute_task 管道（失败语义具体化） | `migrations/005_task_table.sql` + `api/routes_contribute.py` + 17 测试 + API.md 端点表收口（16=14 HTTP+2 CLI） | e6c496d |
| T5 | UI 收尾：quality.html（Data & Quality 页，SSR 来源 Tier 表+terms_checked_at）+ jd.html 贡献区（D7 opt-in 默认未勾）+ app.js 贡献流水（轮询/失败横幅/一次性 code）+ 导航七页 | `templates/quality.html` + `static/app.js` + 11 测试 | 8fa1b08 |
| T6 | CI 增强：ci.yml + docker build job（C6 仅构建不推送、与 test 并行）+ Phase 9 CI 首跑绿同步确认（run 35686447520 @6b1d277） | `.github/workflows/ci.yml` | 07ea77a |
| T7 | 文档终版：README 七段重写（D8 红线）+ DATA.md/DEVELOPMENT.md 新建（D9）+ ARCHITECTURE/API/EVALUATION/DESIGN_DECISIONS 更新 + cid 9→1 同步 + snapshot#1 重建 + 零偏差抽查 12 项全过 | `README.md` + `docs/*.md` | df4db03 |
| T8 | 全新环境自演示：DEMO.md 脚本（C5 脚本入库录制产物不入库）+ 干净目录三命令验证 + 浏览器七页全流程走查（两缺陷当次修复） | `docs/DEMO.md` + `ingest/contribute.py`（缺陷#2 修复）+ 走查记录见 §4 | f738982 |
| T9 | 收口：本 Review + ROADMAP/HANDOVER 同步 + 全量回归 540 绿 | 本 commit | — |

同期穿插（非计划任务，2026-09-22 卷事故恢复的收尾，如实记录）：
- **e90c76b** E2 物化改内容寻址——事故 R3 重跑暴露 `job#N` id 直用在库重建后 24/24 引用漂移全对错配（ρ 0.445 假性 block）；修复后 E2 pass（ρ=0.8277 基线带内）+ 回归锚 `test_materialize_job_id_drift_guard`；全记录 DECISION_LOG D-2026-09-22-20。
- **4622f63** HANDOVER 更新至 Phase 10 收官 + §13 迁移清单（账号切换）。

测试：**540 全绿**（Phase 10 收口 505 → +35：E2 修复锚 +1 / T3 +9 / T4 +14 / T5 +11）。

## 1. 验收核验表（对照 ROADMAP Phase 11 + 计划验收清单）

| 验收项 | 结果 | 证据 |
|---|---|---|
| 全新环境 clone 后按 README 三条命令内跑通 | ✅ | T2 本机干净重拉：`docker compose up -d` 单命令全栈 health ok/db:true/llm configured + 重启幂等 + 容器内 MIGRATIONS_DIR=/app/migrations 实证；T8 干净目录三命令（clone/cp .env/compose up）再验 + entrypoint 三段日志预期 + 幂等重启（DEMO.md §1 固化） |
| CI 全绿（远端首跑） | ⚠️ 部分达成 | Phase 9 test job 首跑绿已确认（run 35686447520 @6b1d277：test completed success + e1 skipped 属正常——Phase 9 遗留验收项闭环）；**Phase 11 的 docker build job 未在远端执行过**（Phase 10/11 共 18 笔待 push，push 需用户批准）——本地仅 YAML 解析三 job 结构验证，远端首跑绿为遗留开放项（§5） |
| 文档与实现零偏差抽查 | ✅ | T7 抽查 12 项全过（README 命令逐条可执行 / API.md 端点表与 routes_*.py 13 端点一一对应 / ARCHITECTURE 与 compose 一致 / DATA.md 数字全部 psql 实查锚定 / ADR 12 份状态核对 / 禁用词扫描 0 命中 / cid 引用分流核实）；T9 复核：API.md 16 行=14 ✅+2 🔧、DB 实查 202 岗（201 批次+1 E2 物化，DATA.md §2 如实记载）与 §13.3 一致 |
| 面试三问三文档可答 | ✅ | 数据从哪来（DATA.md：三通道×Tier/批次历史/口径/事故全记录）/ 为什么这么设计（ADR-001~012 全部已接受/已复议）/ 怎么证明有效（EVALUATION.md：E1 0.8644 warn·E2 0.8277 pass·E3 0.6497 pass 库内真实基线） |
| API.md 16 端点契约收口 | ✅ | 14 HTTP 实现（Phase 10 十端点 + T3 三端点 + T4 contribute/tasks）+ 2 管理端点标注 CLI 通道（jd/import、ingest/adzuna——C1 裁决：无鉴权 HTTP 暴露管理面扩大攻击面）；API.md §1 实现状态列全标 |
| Data & Quality 页七页导航齐 | ✅ | T5 quality.html + /quality 路由 + base.html 导航七链接（test_web_pages 断言六→七）；SSR 来源 Tier 表 + terms_checked_at 直出 + JS 填充五指标/eval 历史 |
| 全量回归绿 + 六维自检 | ✅ | 540 passed, 0 skipped（2026-09-24 T9 复跑，--basetemp 纪律）；§3 |

## 2. 口径裁决落地核对（C1-C7）

| # | 裁决 | 落地 |
|---|---|---|
| C1 | 做 5 裁 2（contribute/tasks/quality/eval/deletion 做；import/adzuna 裁 CLI 通道） | ✅ 五端点全部落地（T3/T4）；两管理端点 API.md 端点表 🔧 CLI 标注（§1 总表 16=14+2） |
| C2 | 异步 = DB 任务表 + BackgroundTasks（否决 celery/rq/纯内存） | ✅ migration 005 task 表（uuid/status CHECK/result jsonb）；单进程 uvicorn 跑通全闭环；deletion_code 持久不因重启丢失 |
| C3 | 连接池维持无池（D1 复议关闭） | ✅ DECISION_LOG D-2026-09-18-19：compose 不改变 §0 本地单用户语义，引池回归成本高于收益 |
| C4 | entrypoint 自动 migrate+seed+serve（幂等）；compose environment 注入服务名连接串 | ✅ 三步幂等 fail-fast；用户 .env 零改动（T2 验收用例）；重启幂等 T2/T8 双验 |
| C5 | DEMO 脚本入库、录制产物不入库 | ✅ docs/DEMO.md（0 前置条件表+三命令+七页操作+常见问题）；走查记录固化本 Review §4；录制（用户侧执行）不阻塞验收 |
| C6 | CI 加 docker build job（build only、并行不阻塞） | ✅ ci.yml 三 job（test/e1/docker）；compose 全栈 e2e 不进 CI（时长+Docker Desktop 依赖，T8 手动覆盖）；远端首跑待 push（§5） |
| C7 | 演示数据可选导入（空库灰态也算过） | ✅ DEMO.md §2 可选 batch_1 导入段（预期报告数字写明）；README Demo 段同口径 |

冻结决策抽查：D5 一次性展示（task.result 首查置 null、DB 本体只存哈希——T8 服务端实证）、D7 opt-in 默认未勾（T5 测试锚定）、D8 README 七段（T7 禁用词扫描 0 命中）均与实现一致。

## 3. 六维自检

### Product —— 真的解决问题吗？
"clone 下来三条命令能跑"落地：全新目录 clone → cp .env → compose up，
entrypoint 自动迁移+seed+起服，health 返回即用（T8 实测）。C1 延后
清单的契约收口完成——贡献→一次性删除码→删除闭环（M3/M11）走通，质量与评测
透明度页（七页导航）把"数据从哪来/怎么证明有效"变成产品界面而非
README 里的承诺。

### Engineering —— 过度设计了吗？
克制点：异步任务用 DB 表 + BackgroundTasks 而非消息队列（C2）；
compose 长驻进程不引入连接池（C3 维持无池，复议有记录）；Dockerfile
单阶段无多阶段构建/无 buildx 缓存；CI docker job 只 build 不推送
（无 registry 凭证依赖）；管理端点裁为 CLI 通道而非全量 HTTP 化（C1
收缩攻击面）。新增基础设施三件（Dockerfile/entrypoint/ci job）全部
服务验收项，无预留性设计。

### AI —— LLM 被滥用了吗？
本阶段零新增 LLM 路径：contribute 管道内的抽取是 Phase 3 既有通道
（B1：入库唯一通道须 consent）；quality/eval/deletion/tasks 四端点
零 LLM。D4 失败语义把"LLM 抽取失败"与"job 入库失败"分开——抽取
失败任务仍 completed + extraction_status=pending 明示（删除权合规
优先，CLI backfill-extraction 可补抽），诚实降级不静默。

### Data —— 数字真实吗？
文档数字全部实查锚定：DATA.md 库快照 202 岗 = 201 批次导入 + 1 条
E2 评测物化（含第 202 条的来源与日期，psql 可复核）；T8 走查后
deletion_code 表 0 残留、质量四率回基线（贡献→删除全闭环无痕验证）。
走查缺陷 #2（PII 处置记录低报）恰是"数字真实性"缺陷——质量报表
hit_rate 曾把真实处置记为 0.0，修复后透传本通道真实扫描报告。

### Evaluation —— 结果可验证吗？
- 540 测试全绿含本阶段 +35（contribute 17/quality+eval+deletion 9/
  UI 11/E2 锚 1），0 skipped（Docker 在运行，无假绿）
- 全新环境走查（T8）是"文档可执行性"的评测：DEMO 初稿即踩中
  空标题 quarantine 语义坑——文档作者自己会踩的坑就是读者必踩的，
  修复方式是 UI 提示 + DEMO 补段而非改契约语义
- CI 验收的诚实边界：docker build job 远端首跑未发生（依赖 push
  审批），本地 YAML 结构验证不能替代远端运行——如实记开放项

### Resume —— 简历价值？
可讲：容器化交付的完整判断链（镜像基线/entrypoint 幂等/环境注入
优先级/端口红线延续到 compose 层）；"做 5 裁 2"的 API 面收敛决策
（管理面不上无鉴权 HTTP）；一次性删除码的防探测设计（明文只在
task.result 首查存在，DB 永远只存哈希，404 字节级一致）；PII 处置
记录低报缺陷的发现-归因-修复（jsonb || 后写覆盖二次扫描空报告）；
以及"自演示脚本入库、录制产物不入库"的可复现性取舍。

## 4. 全新环境自演示走查（T8，2026-09-24）

环境：干净目录重新 clone + cp .env + `docker compose up -d`
（三命令）；随后浏览器七页全流程（合成简历 + 含手机号合成 JD 供
PII 演示）。DEMO.md 为固化脚本（C5），本节为执行记录与发现。

### 4.1 步骤与结果（DEMO.md §3 对应）

| # | 步骤 | 结果 |
|---|---|---|
| 1 | 三命令起全栈 | ✅ entrypoint 三段日志（db-upgrade 4 迁移/seed 幂等/uvicorn 起服）+ health `{"status":"ok","db":true,"llm":"configured"}`；幂等重启验证通过 |
| 2 | 可选 batch_1 导入 | ✅ 50 条导入报告与 DEMO.md §2 预期一致 |
| 3 | 浏览器 3.1-3.7 七页全流程 | ✅ 简历→画像→JD 分析→贡献（真实提交含 PII JD）→匹配 60.5 四维完整→推荐/市场→Data & Quality 页；控制台零 JS 错误 |
| 4 | 3.8 删除贡献收尾 | ✅ 一次性码 N4CD-AWEA（job 205·phone×1+contact×1·extraction done）→ DELETE 204 → 重复 DELETE 404（一次性+防探测）→ active 回 202/deletion_code 表 0 残留/质量四率回基线；市场 N 202→203（贡献进统计闭环）→删除后回 202 |

### 4.2 走查发现的真实缺陷（2 项，全部当次修复）

| # | 缺陷 | 根因 | 修复 |
|---|---|---|---|
| 1 | 贡献流程空标题后果 UI 不可发现（走查实录：DEMO 初稿照界面操作空标题提交 → quarantine failed——属契约内语义 §2.2 与 CLI 同口径，但贡献区未说明后果，连 DEMO 初稿都踩坑） | UI 可发现性缺口，非契约缺陷 | jd.html 贡献区加提示"岗位标题为空时贡献将进入质检隔离队列（人工复核，不入统计）"+ DEMO.md 3.2 补标题必填说明与可选 quarantine 诚实失败演示段 |
| 2 | PII 处置记录低报（任务结果 phone×1 但 job.parsed_metadata.pii_redaction.hits 落库为空 {}——质量报表 scan_count=1/hit_rate=0.0 低报真实处置） | contribute_jd 先脱敏再把已脱敏文本交 process_record，process_record 对干净文本二次扫描恒零命中，redact() 恒返回 report 故空 hits 仍入库 | contribute.py 入库后 parsed_metadata UPDATE 增写 pii_redaction=本通道真实扫描报告（jsonb \|\| 后写覆盖二次扫描空报告）+ test_contribute_pii_redaction_passthrough 扩展落库元数据断言（回归锚） |

走查另证（符合预期，非缺陷）：D5 一次性语义服务端实证（轮询 GET 后
task.result 置 null）；empty_title quarantine 失败横幅如实渲染（不
静默）；Adzuna 归属与灰态口径延续 Phase 10。

## 5. 遗留与移交

| 项 | 状态 | 处置 |
|---|---|---|
| CI docker build job 远端首跑绿 | ⏳ 待 push | Phase 10/11 共 18 笔本地待审批推送（origin/master 现至 6b1d277 = Phase 9 收口）；push 后盯三 job 首跑（test+docker 双绿、e1 skipped 正常） |
| E1 dispatch 验收 | ⏳ 待 push + secret | GitHub 配 `LLM_API_KEY` 后手动 dispatch 一次（Phase 9 遗留延续） |
| E3 标注双人复核 | ⏳ 用户 + 同学 | 不阻塞（Phase 8 遗留延续） |
| Adzuna 首批拉取 | ⏳ 待办 | global 市场 N=0 灰态（README Limitations 如实声明）；250 req/day 额度节奏 |
| 自演示录制 | ⏳ 用户侧执行 | DEMO.md 脚本已入库（C5），Windows 录屏工具链用户执行，产物不入库 |
| MVP 全部 11 项（M1-M11）| ✅ 达成 | 至此 MVP 范围内无未实现项；后续方向（鉴权/公网部署/PDF 简历/GitHub 分析 v2/多用户）见 ROADMAP 与 README Roadmap 段 |

## 6. 下一步

MVP（Phase 0-11）收官。候选方向（均为 MVP 外，动工前先写计划与 ADR）：
v2 功能（GitHub 分析/Adzuna global 数据/时间序列趋势）、部署强化
（认证与速率限制——§0 公网部署前提）、数据运营（批次 4+ 收集、
E1 prompt recall 迭代——禁止为跑分过拟合评测集）。
