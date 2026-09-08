# Phase 10：Dashboard（M10 六视图 + 端到端流程）实施计划

> **Goal**：FastAPI 只读为主的服务层 + 六视图 Dashboard + PRODUCT_SPEC §3 端到端用户流程走通（简历粘贴 → 画像 → JD 粘贴 → 匹配 → 缺口 → 推荐 → Dashboard），每个数字可点击溯源、样本量守门在 UI 呈现。
> **Architecture**：两层——`api/` FastAPI 应用（create_app 工厂 + 每请求连接依赖 + Jinja2 SSR 页面路由与 /api/* 并存）；前端零框架（Jinja2 模板 + 原生 JS + 手写 SVG/CSS 图表，无构建步骤无 CDN）。API 层零计算：只组装既有 service 层输出（stats/profile/match/gap/recommend/analyzer），数字与 evidence_ref 全部透传。
> **Tech Stack**：Python 3.12 + psycopg + pytest（既有）；**新依赖 fastapi + uvicorn + jinja2**（ADR-011；httpx 已有——TestClient 直接可用）。

## Context

- **现状**：CLI-only（20+ 命令），服务层齐备且全部有测试（443 绿）；API.md 契约 Phase 1 冻结（16 端点 + 统一错误体 + §0 部署红线：本地单用户无鉴权）；UI_SPEC Phase 1 冻结（七页信息架构 + §2.1 六视图规格 + §3 交互纪律）。
- **数据**：主库 china N=201（snapshot #4，quality=high）；global 市场 Adzuna 未拉取（预期 N<30——正好作为守门灰态的真实演示）。
- **关键缺口**：`match_score` 仅支持 job_id（契约 §2.8 允许 jd_text/job_id 二选一）；e2e 流程要求"粘贴 JD → 匹配"不断裂，且入库须 consent（B1 纪律）——粘贴文本无法走 job_id 模式。

## 口径裁决（先落 DECISION_LOG D-2026-09-08-18，再动代码）

| # | 冲突/空白 | 裁决 |
|---|---|---|
| C1 | **范围**：UI_SPEC 七页 + API 16 端点全做 vs ROADMAP Phase 10 产出（六视图 + e2e 流程） | **10 端点 + 6 页**。延后 Phase 11：contribute/import/adzuna 三管道端点 + tasks 异步查询（CLI 已覆盖，UI 贡献区 PRODUCT_SPEC §3 标"可选"）；quality/report + eval/results（M11 标记，Phase 11 与 Docker/README 一并收口）；Data & Quality 页随 M11 端点走 |
| C2 | 前端技术选型（UI_SPEC"服务端渲染或轻前端均可"+ ROADMAP 自检"无花哨前端框架依赖"） | **Jinja2 SSR + 原生 JS + 手写 SVG/CSS 图表**。零框架、零构建步骤、零 CDN（离线可用）；雷达/条形全部手写（D6） |
| C3 | 新依赖纪律（HANDOVER 纪律 2：新增依赖先补 ADR） | fastapi>=0.115 + uvicorn + jinja2 → **ADR-011**（引入理由：类型化契约 + TestClient 复用 httpx + SSR 一体；备选 Flask/纯静态被否原因记录）；`serve` 默认绑定 127.0.0.1（API.md §0 部署红线落地） |
| C4 | **match jd_text 模式**：契约 §2.8 二选一，但服务层只有 job_id 模式 | 新增 `match_score_text()`：jd_text → `analyze_jd`（无状态抽取）→ 组装 reqs → 复用 `compute_match` 纯函数 → **不落库**（无 consent 不入库，B1 纪律）；与 job_id 模式对同一 JD **同分一致性测试锚定**（FakeLLM 固定输出，contribute 入库后双模式对比） |
| C5 | "无前端硬编码数字"验收（ROADMAP 验收原文）操作化 | 渲染测试（fixture 数字必出现在 HTML、N<30 灰态占位文案）+ T9 模板人工抽查；不做模板自动扫描（页数有限，YAGNI） |
| C6 | 会话模型（MVP 无账号，画像需跨页串起） | candidate_id 由前端 **localStorage 持有**，画像/匹配/缺口/推荐请求显式携带（契约本就显式 id）；画像删除走 UI 二次确认（UI_SPEC §2.3）；**匹配概览数据源 = localStorage 缓存最近一次 /api/match 响应**（契约无"最近匹配"查询端点，不加新端点——数据仍来自 API，满足验收口径；清缓存即空态提示先去匹配页） |
| C7 | LLM 端点测试策略（jd/analyze、resumes/analyze 依赖真实 LLM） | 单测一律 **FakeLLM 三分支**（成功/抽取失败/超时）；真实 e2e 一次手动走查记录 PHASE_10_REVIEW（Phase 8 §4 先例）。match `?explain=true` 走 LLM 叙事但**非默认**（默认确定性模板，UI_SPEC §2.4"数字由 breakdown 渲染"） |

## 冻结的设计决策

| # | 决策 |
|---|---|
| D1 | `create_app()` 工厂 + `get_conn` 每请求连接（FastAPI Depends；本地单用户，不引入连接池——YAGNI，Phase 11 compose 若需再议） |
| D2 | 错误映射（统一错误体 API.md §0）：`VALIDATION_ERROR` 422 / `NOT_FOUND` 404 / `LLM_EXTRACTION_FAILED`·`LLM_TIMEOUT` 502；`SAMPLE_INSUFFICIENT` 双口径按契约原文——market/skills 返回 **200 + insufficient:true**（§2.11 冻结，前端不当错误处理），recommendations 返回 **422 错误体**（§2.10 拒推） |
| D3 | API 层零计算：只组装/包装 service 输出；响应结构对齐 API.md 契约（CLI 响应超集字段裁剪——§2.5 已有先例说明，schemas.py 承担） |
| D4 | `skillgap serve [--host 127.0.0.1] [--port 8000]`（uvicorn programmatic；host 显式传参才可改绑——默认拒绝 0.0.0.0） |
| D5 | 样本量守门 UI：N<30 → 灰色占位 + "样本量不足以判断趋势（N=xx）"（UI_SPEC §2.1 原文案），不隐藏、不降级为无标注数字；由 insufficient/sample_size 字段驱动 |
| D6 | 图表全部手写：雷达 = SVG 六边形网格 + required_level/actual_level 双多边形叠加；条形（热门技能频率 / 匹配四维 breakdown）= CSS div 宽度；不引入图表库 |
| D7 | templates/static 打包进 `api/` 包（pyproject package-data 增 `api/templates/*.html` + `api/static/*`——Phase 11 docker compose 直接受益） |
| D8 | 页面路由与 API 同 app：`/`（Dashboard）`/resume` `/jd` `/match` `/recommend` `/market` 六页 + `/static`；base.html 常驻市场选择器 + 数据窗口标注（UI_SPEC §1 全局常驻） |
| D9 | 测试纪律：TestClient（httpx 已有）+ 既有 conftest test 库 fixtures + FakeLLM；API 测试不触真实 key、不触主库 |
| D10 | 溯源交互：evidence_ref → `/api/market/skills/{skill}/evidence` 证据列表（弹层或页内展开）；JD 页证据片段高亮原文位置（UI_SPEC §2.2）够用即止 |

## 文件结构

```
docs/adr/ADR-011-fastapi-introduction.md   # 新依赖 ADR（纪律 2）
src/skillgap/api/                           # 新包
  __init__.py
  app.py            # create_app + /api/health + 统一错误体 + 页面路由挂载
  deps.py           # get_conn（每请求连接）
  schemas.py        # 请求/响应模型（对齐 API.md，超集裁剪）
  routes_market.py  # §2.11 market/skills + §2.12 evidence
  routes_profile.py # §2.5 resumes/analyze + §2.6 profile GET + §2.7 DELETE
  routes_match.py   # §2.8 match（job_id/jd_text 二模式）+ §2.9 gaps
  routes_recommend.py # §2.10 recommendations
  routes_jd.py      # §2.1 jd/analyze（无状态不落库）
  templates/        # base/dashboard/resume/jd/match/recommend/market.html
  static/           # style.css / app.js / radar.js
src/skillgap/match/service.py               # +match_score_text()（C4）
src/skillgap/cli.py                          # +serve（D4）
pyproject.toml                               # +依赖 + package-data（D7）
tests/test_api_app.py        # 骨架：health/错误体/404/静态
tests/test_api_market.py     # 频率/守门口径/溯源
tests/test_api_profile.py    # FakeLLM 三分支/画像/删除
tests/test_api_match.py      # 双模式/一致性锚定/explain 可选
tests/test_api_recommend.py  # ROI/拒推口径
tests/test_api_jd.py         # 无状态断言/失败明示
tests/test_web_pages.py      # 六页渲染：fixture 数字/灰态/无硬编码
```

## 任务分解（TDD）

| # | 任务 | 交付 | 验收 |
|---|---|---|---|
| T1 | ADR-011 + DECISION_LOG D-18 + FastAPI 骨架 | ADR-011；pyproject 依赖+package-data；`api/app.py`（create_app/get_conn/health/统一错误体）+ `cli.py serve`；`test_api_app.py`（≥5 项） | pytest 绿；`skillgap serve` 起服后 `curl 127.0.0.1:8000/api/health` 返回 ok/db:true；ADR 与 D-18 落档 |
| T2 | 市场端点 | `routes_market.py` + `test_api_market.py`（≥6 项：正常频率结构/insufficient 200 口径/N<30 字段/未知技能 404/evidence 溯源结构/切片过滤） | fixture 测试绿；真实库 curl china（N=201 正常）与 global（预期 insufficient 灰态原料） |
| T3 | 画像端点 | `routes_profile.py` + `test_api_profile.py`（≥8 项：FakeLLM 成功/失败 502/长度 422/新 candidate 创建/profile 结构含证据链/NOT_FOUND/DELETE 204/再查 404） | 响应按 §2.5 契约裁剪（超集字段剥离断言） |
| T4 | 匹配 + 缺口（含 C4 text 模式） | `match/service.py +match_score_text()`（复用 compute_match，不落库）+ `routes_match.py` + `test_api_match.py` + text 模式服务层测试（≥8 项：job_id 模式/jd_text 模式/**双模式同分一致性**/explain 默认模板/explain=true 走 LLM 拦截/gaps 双模式/NOT_FOUND/无技能 JD invalid） | FakeLLM 测试绿；text 模式结果与 job_id 模式逐字段相等（同 JD 同抽取器） |
| T5 | 推荐 + JD 分析端点 | `routes_recommend.py` + `routes_jd.py` + `test_api_recommend.py` + `test_api_jd.py`（≥8 项：priority_items 结构/预算过滤/INSUFFICIENT_MARKET_DATA→422 错误体/jd 长度校验/成功结构/**库无新行断言**/失败 502 明示/soft_requirements 透传） | FakeLLM 测试绿；jd/analyze 前后 `SELECT count(*) FROM job` 不变 |
| T6 | 前端骨架 + Dashboard 六视图 | `templates/base.html+dashboard.html` + `static/`（style/radar）+ 页面路由 + `test_web_pages.py`（≥6 项：六视图区块存在/fixture 数字出现/N<30 灰态占位文案/市场选择器常驻/雷达 SVG 双多边形/无硬编码技能名） | TestClient 渲染断言绿；真实库起服人工核对六视图 |
| T7 | 流程页 + e2e 串联 | `templates/` resume/jd/match/recommend/market 五页 + `static/app.js`（localStorage candidate_id、表单提交、失败横幅）+ 渲染测试扩展（≥8 项） | 每页渲染测试绿；流程页间跳转可用（链接指向核查） |
| T8 | 溯源交互 + 真实 e2e 手动走查 | 证据弹层（evidence 端点驱动）+ JD 证据高亮；**真实 LLM 全流程走查**（简历粘贴→画像→JD 粘贴→匹配→缺口→推荐→Dashboard 六视图） | 走查记录（步骤+截图+发现）入 PHASE_10_REVIEW §4；发现的问题如实修复或记录 |
| T9 | 收口 | PHASE_10_REVIEW.md（六维自检+验收核验表）+ ROADMAP/HANDOVER 状态 + API.md 各端点补"实现备注"（text 模式/裁剪说明）+ 全量回归 | 443+新增全绿；文档同步零偏差抽查 |

## 风险与对策

| 风险 | 对策 |
|---|---|
| 前端范围失控（UI_SPEC 七页全做+交互打磨无底洞） | C1 裁决 6 页；UI_SPEC §3 纪律兜底（桌面优先/无动画/够用即止）；T6-T7 每页有渲染测试防烂尾 |
| match text 模式与 job_id 模式口径漂移 | C4 一致性测试锚定（同 JD 双模式逐字段相等）；text 模式复用 `compute_match` 纯函数，无第二套公式 |
| fastapi/jinja2 与既有 pydantic v2 兼容 | fastapi>=0.115 原生 pydantic v2（项目已 pydantic>=2.7）；T1 骨架先冒烟 |
| 每请求 psycopg 连接开销 | 本地单用户可忽略；D1 明确不引入池（Phase 11 复议点预留） |
| 模板硬编码数字混入（验收红线） | C5：渲染测试断言 fixture 数字必现 + T9 人工抽查全部模板 |
| LLM 真实跑失败/超时打断 e2e 走查 | UI 失败横幅明示（UI_SPEC §2.2）不静默；走查可重试，失败本身也是"诚实降级样式"的验证素材 |
| CI 时长增长（新测试 ~40 项） | API 测试全 fixture/FakeLLM 无真实调用；预期增量 <30s，PR 快检口径不变 |

## 验收清单（对照 ROADMAP Phase 10 + UI_SPEC + PRODUCT_SPEC §3）

- [ ] 六视图数据全部来自 API（无前端硬编码数字）——T6 测试 + T9 抽查
- [ ] 样本量守门在 UI 呈现（N<30 灰色占位 + 文案）——T2 口径 + T6 渲染测试
- [ ] 端到端用户流程走通（PRODUCT_SPEC §3：简历→画像→JD→匹配→缺口→推荐→Dashboard）——T8 真实走查
- [ ] 每个数字可点击溯源（evidence_ref → JD/证据页）——T8
- [ ] 全量回归绿 + PHASE_10_REVIEW 六维自检——T9
