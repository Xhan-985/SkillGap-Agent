# Phase 11：Docker + CI + Documentation（发布就绪）实施计划

> **Goal**：clone → 三条命令内跑通（compose 全栈 + 演示数据导入 + serve）+ CI 全绿 + 文档终版（README/DATA/DEVELOPMENT 等，面试三问可答）+ C1 延后端点与 Data & Quality 页收口。
> **Architecture**：三线并行收尾——① 部署线：Dockerfile（app 镜像）+ compose 全栈（postgres + app，entrypoint 自动 migrate+seed+serve）；② 契约线：API.md 16 端点收口（新增 contribute/tasks/quality/eval/deletion 5 个，import/adzuna 裁剪为 CLI 通道）+ Data & Quality 页；③ 文档线：README 七段 + DATA.md/DEVELOPMENT.md 新建 + 既有文档终版核对。
> **Tech Stack**：既有全部（零新 Python 依赖）；新增基础设施：Dockerfile + compose app service + CI docker build job（非代码依赖，ADR-012 记录部署决策）。

## Context

- **现状**：Phase 10 收官（505 测试绿）；CLI 20+ 命令 + FastAPI 10 契约端点 + 六页 SSR Dashboard；master 本地领先远端 17 笔（Phase 9/10 未推送——CI 首跑绿是本阶段验收项，**push 时点由用户决定**）。
- **CI**：Phase 9 T5 已建 workflow（test 全量 + E1 dispatch），**从未在远端执行过**；python 3.11（pyproject `requires-python >= 3.11` 兼容，无需改动）。
- **C1 延后清单**（Phase 10 裁决移交）：contribute/import/adzuna 管道端点 + tasks 异步查询 + quality/report + eval/results + Data & Quality 页。
- **D1 复议点**（Phase 10 预留）：compose 长驻进程是否引入连接池。
- **README 现状**：仅标题（纪律"Phase 11 统一补，不提前写营销文档"）。
- **文档缺口**：DATA.md / DEVELOPMENT.md 不存在（ROADMAP Phase 11 产出要求终版）；ARCHITECTURE.md 停留在 Phase 8 前（FastAPI/LangGraph/RAG 未入图）。

## 口径裁决（先落 DECISION_LOG D-2026-09-18-19，再动代码）

| # | 冲突/空白 | 裁决 |
|---|---|---|
| C1 | **端点范围**：C1 延后清单 6 端点全做 vs Phase 11 主线（Docker+CI+文档） | **做 5 裁 2**。做：jd/contribute（§2.2，F12 核心机制）+ tasks/{id}（§2.2 内嵌）+ quality/report（§2.13）+ contributions DELETE（§2.14）+ eval/results（§2.15）；**裁：jd/import（§2.3）+ ingest/adzuna（§2.4）**——管理操作，CLI 已覆盖，无鉴权 HTTP 暴露管理面反而扩大攻击面（API.md §0 本地单用户红线），API.md 端点表标注"CLI 通道" |
| C2 | **异步任务实现**（契约 202 + task_id）：celery/rq vs 内存 vs DB | **DB 任务表 + FastAPI BackgroundTasks**（migration 005 新表 task；单进程 uvicorn 够用）。否决 celery/rq（新依赖+broker 运维，YAGNI）；否决纯内存（deletion_code 须持久，重启丢失不可接受） |
| C3 | **D1 连接池复议**：compose 长驻进程是否引入 psycopg_pool | **维持无池**。API.md §0 部署语义不变（本地单用户，compose 只是免去本机装 PG）；每请求连接容器网络开销 ~ms 级；引入池需回归全部端点测试，收益低于成本。复议结论落 DECISION_LOG 关闭 D1 |
| C4 | **compose 入口编排**：entrypoint 自动 migrate+seed vs 手动分步 | **entrypoint 自动**（db-upgrade + seed 幂等，重启安全）——"三条命令内跑通"验收驱动；compose `environment` 注入 `DATABASE_URL=postgresql://skillgap:skillgap@postgres:5432/skillgap`（服务名），**用户 .env 无须为容器改连接串** |
| C5 | **自演示录制**（ROADMAP 产出"一次完整自演示录制"） | **DEMO.md 脚本入库**（步骤+命令+预期输出），**录制产物不入库**（个人资产；Windows 录屏工具链用户侧执行）；T8 走查记录入 PHASE_11_REVIEW §4 |
| C6 | **CI 增强**：是否加 Docker 相关 job | **加 docker build job**（只 build 不 push，无 registry 凭证依赖；与 test job 并行不阻塞）；E1 dispatch 维持；compose 全栈 e2e 不进 CI（时长+Docker Desktop 依赖，留给 T8 手动） |
| C7 | **演示数据**：全新环境六视图要有数据须 import | README Demo 段写明可选步骤 `docker compose exec app skillgap import --file data/batch_1.csv`（批次 CSV 已入库跟踪）；空库跑通也算过（灰态即诚实降级演示） |

## 冻结的设计决策

| # | 决策 |
|---|---|
| D1 | Dockerfile 单阶段 `python:3.12-slim`：非 root 用户 + `pip install .`（package-data 随包，Phase 10 D7 已备）+ ENTRYPOINT 脚本 LF 强制（PowerShell CRLF/BOM 已知坑兄弟版） |
| D2 | compose `app` service：`depends_on: postgres: condition: service_healthy`；端口 **`127.0.0.1:8000:8000`**（部署红线延续——compose 也不默认对外网开放）；redis 维持现状（不接入 app，缓存走 DB llm_cache） |
| D3 | entrypoint = `db-upgrade` → `seed` → `uvicorn`（全幂等）；迁移失败即退（fail-fast 不带病起服） |
| D4 | 任务表 task（migration 005）：`id uuid / kind / status(pending→running→completed|failed) / result jsonb / error / created_at / updated_at`；BackgroundTasks 内自建连接（不复用请求连接）；失败任务 status=failed + error 明示（不静默——纪律对齐） |
| D5 | **deletion_code 一次性展示语义**：contribute 完成后 task.result 存明文；GET /api/tasks/{id} **首次返回后即将 result 中 deletion_code 置 null**（"已展示，请使用已保存的 code"）——DB 本体仍只存哈希（防探测，§2.14 纪律不变） |
| D6 | Data & Quality 页对齐 Phase 10 模式：SSR 骨架 + app.js fetch 填充（quality/report + eval/results + market/skills 的 source_distribution 组装）；导航六页 → 七页 |
| D7 | JD 分析页贡献区（UI_SPEC §2.2）：分析成功后出现复选框（默认未勾）+ 提交 → POST contribute → 轮询 task → deletion_code 一次性展示弹层；交互够用即止（§3 纪律） |
| D8 | README 结构冻结七段：Problem / Solution / Architecture / Demo（三条命令）/ Evaluation / Limitations / Roadmap；**红线：技术向非营销**（无"强大的""业界领先"类话术；Limitations 如实写——global N=0 / 单用户无鉴权 / 评测集规模边界） |
| D9 | 文档终版范围：**新建** DATA.md（面试三问之一：数据从哪来——三通道/Tier/批次历史/口径）+ DEVELOPMENT.md（环境/测试/CI/迁移指南）；**更新** ARCHITECTURE.md（补 FastAPI+LangGraph+RAG 现状图）/ API.md（import+adzuna 标注 CLI 通道 + 新端点实现备注）/ EVALUATION.md（索引核对）/ DESIGN_DECISIONS.md（ADR-012 入索引）；**核对** ADR-001~012 全部"已接受/已复议"状态 |
| D10 | 测试纪律延续：新端点 TestClient + fixture + FakeLLM（contribute 管道内 LLM 抽取用 Fake）；Docker/entrypoint 不写容器内 pytest（手动验证 + CI build 兜底） |

## 文件结构

```
Dockerfile                                    # 新：app 镜像（D1）
docker-compose.yml                            # 改：+app service（D2/D3）
docker/entrypoint.sh                          # 新：migrate+seed+serve（LF）
docs/adr/ADR-012-docker-deployment.md         # 新：部署容器化决策（C2/C3/C4 依据）
migrations/005_task_table.sql                 # 新：task 表（D4）
src/skillgap/api/
  routes_contribute.py                        # 新：§2.2 POST jd/contribute + §2.14 DELETE contributions + GET tasks/{id}
  routes_quality.py                           # 新：§2.13 quality/report + §2.15 eval/results
  routes_web.py                               # 改：+ /quality 页路由
  templates/quality.html                      # 新：Data & Quality 页（UI_SPEC §2.7）
  templates/jd.html                           # 改：+贡献区（D7）
  static/app.js                               # 改：+contribute 轮询 + 质量页渲染
README.md                                     # 改：七段终版（D8）
docs/DATA.md                                  # 新（D9）
docs/DEVELOPMENT.md                           # 新（D9）
docs/DEMO.md                                  # 新：自演示脚本（C5）
.github/workflows/ci.yml                      # 改：+docker build job（C6）
tests/test_api_contribute.py                  # 新：contribute/tasks/deletion（含 D5 一次性语义）
tests/test_api_quality.py                     # 新：quality/eval 端点
tests/test_web_quality.py                     # 新：质量页渲染
```

## 任务分解（TDD）

| # | 任务 | 交付 | 验收 |
|---|---|---|---|
| T1 | 计划落档 + ADR-012 + DECISION_LOG D-19 | 本文档 + ADR-012（容器化：entrypoint 策略/无池复议/镜像基线）+ D-2026-09-18-19（C1-C7 裁决 + D1-D10 冻结 + Phase 10 D1 连接池复议关闭） | 三份落档 |
| T2 | Docker 化 | Dockerfile + entrypoint.sh + compose app service + `.env.example` 备注 | 本机干净重拉：`docker compose up -d` 单命令起全栈，health ok / db:true；重启幂等；**三条命令清单**（clone / cp .env / compose up）验证记录 |
| T3 | 同步收尾端点 | routes_quality.py + routes_contribute.py 的 DELETE contributions + tests（≥8 项：quality 五指标结构 / eval 历史列表+版本三元组 / deletion 204/404 防探测不区分 / NOT_FOUND） | fixture 测试绿；真实库 curl 验证 |
| T4 | 任务基础设施 + contribute | migration 005 + POST jd/contribute（202 + BackgroundTasks）+ GET tasks/{id}（D5 一次性 code）+ tests（≥10 项：202 结构 / consent=false 拒绝 / FakeLLM 管道 completed + job 入库 / deduplicated 透传 / quarantine 明示 / 任务失败 error 不静默 / deletion_code 首查返回二查为 null / 未知 task 404 / 复跑幂等） | 端到端 fixture：contribute → task completed → job 表新行 + deletion_code 一次性语义断言 |
| T5 | UI 收尾 | quality.html + /quality 路由 + jd.html 贡献区 + app.js（轮询/弹层/质量页渲染）+ 导航七页 + tests（≥8 项：五指标卡渲染 / 来源分布 / terms_checked_at 呈现 / 贡献复选框默认未勾 / task 结果弹层 / 导航七链接 / 无硬编码数字） | 渲染测试绿；真实库人工核对质量页 |
| T6 | CI 增强 + 首跑绿（**依赖用户批准 push**） | ci.yml + docker build job（build only）+ workflow 注释更新 | push 后远端 CI 首跑全绿（test + docker 双 job；e1 dispatch 显示 skipped 属正常）；16+ 端点时代首个远端绿截图留档 |
| T7 | 文档终版 | README 七段 + DATA.md + DEVELOPMENT.md + ARCHITECTURE/API/EVALUATION/DESIGN_DECISIONS 更新 + ADR-001~012 状态核对表 | **零偏差抽查表**（≥10 项：README 命令逐条可执行 / API.md 端点表与路由一一对应 / ARCHITECTURE 图与 import 图一致 / DATA.md 数字与库一致） |
| T8 | 全新环境自演示 | DEMO.md 脚本 + 干净目录三命令验证 + 浏览器全流程走查（含 contribute 真实提交 + 质量页）+ 录制（用户执行） | 走查记录（步骤+发现+截图位）入 PHASE_11_REVIEW §4；发现缺陷当次修复或如实记录 |
| T9 | 收口 | PHASE_11_REVIEW.md（六维自检+验收核验表）+ ROADMAP Phase 11 ✅ + HANDOVER 状态同步（含 §13 迁移清单更新）+ 全量回归 | 全量回归绿；文档同步零偏差抽查 |

## 风险与对策

| 风险 | 对策 |
|---|---|
| Docker Desktop 未启动（本机已知：须用户手动启动） | T2/T8 前置检查；测试可能静默 skip 的历史教训——T8 必须真实起容器走查，不信 exit 0 |
| entrypoint.sh 被 git 换行转 CRLF → 容器内 `\r` 报错 | .gitattributes 强制 `*.sh text eol=lf`；Dockerfile 内 `sed` 兜底不可取（治标），入库前 `git ls-files --eol` 核查 |
| compose environment 与 .env 优先级混淆（容器内连 localhost 失败） | compose `environment` 显式注入服务名连接串（优先级高于 env_file）；T2 验收含"用户 .env 不改"用例 |
| BackgroundTasks 与请求连接生命周期（请求关闭后后台仍需连接） | D4：任务内自建连接 + finally 关闭；测试断言任务完成后无连接泄漏（pytest fixture 探活） |
| CI docker build 增时（slim 拉取+pip install ~1-2min） | 与 test job 并行；`cache-from/to` 不引入（无 registry），时长可接受即过 |
| README 膨胀成营销文档 | D8 红线 + T7 抽查表含"禁用词扫描"（强大的/领先/极致等） |
| 任务表 migration 与既有 schema 冲突 | 005 仅新增表零改动既有表；conftest 自动迁移路径覆盖 |
| contribute 真实 LLM 走查失败打断 T8 | FakeLLM 测试兜底 + UI 失败横幅明示；失败重试，失败本身即"诚实降级"验证素材 |

## 验收清单（对照 ROADMAP Phase 11 + MVP M11 + UI_SPEC §2.7）

- [ ] 全新环境 clone 后按 README **三条命令内跑通**——T2 + T8
- [ ] CI 全绿（远端首跑）——T6（前置：用户批准 push）
- [ ] 文档与实现零偏差抽查——T7 抽查表
- [ ] 面试三问三文档可答：数据从哪来（DATA.md）/ 为什么这么设计（ADR-001~012）/ 怎么证明有效（EVALUATION.md）——T7
- [ ] API.md 16 端点契约收口：15 实现 + 2 管理端点标注 CLI 通道（C1 裁决，API.md 端点表更新）——T3/T4/T7
- [ ] Data & Quality 页七页导航齐——T5
- [ ] 全量回归绿 + PHASE_11_REVIEW 六维自检——T9

## 依赖与顺序

```
T1 ─→ T2（Docker）─→ T3（同步端点）─→ T4（任务+contribute）─→ T5（UI）─→ T6（CI+push）─→ T7（文档）─→ T8（自演示）─→ T9（收口）
                                                    ↑ T6 依赖用户批准 push（时点用户定，不阻塞 T7 起步；首跑绿验证在 push 后补）
```
