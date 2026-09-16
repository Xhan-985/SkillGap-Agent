# Phase 10 Review —— Dashboard / API / 前端 验收与六维自检

> 阶段：FastAPI 10 端点 + Jinja2 SSR 六页 + 原生 JS 前端 + 真实 LLM e2e 走查。
> 计划：`docs/plans/2026-09-08-phase10-dashboard.md`（口径裁决 C1-C7 +
> 冻结决策 D1-D10）。

## 0. 交付物清单

| # | 交付 | 位置 | commit |
|---|---|---|---|
| T1 | ADR-011 + FastAPI 骨架（create_app 工厂/统一错误体三 handler/get_conn 每请求连接/health/`serve` CLI 默认 127.0.0.1） | `api/app.py` + `api/deps.py` + `api/errors.py` + `test_api_app.py`（5 测试） | 62bac30 |
| T2 | 市场端点（§2.11 频率 + §2.12 溯源；D3 裁剪 + D10 证据 URI） | `api/routes_market.py` + `test_api_market.py`（8 测试） | 5e09583 |
| T3 | 画像端点（§2.5/§2.6/§2.7；FakeLLM 三分支） | `api/routes_profile.py` + `test_api_profile.py`（8 测试） | 6b8a30c |
| T4 | 匹配+缺口端点 + `match_score_text()`（C4 双模式同分锚定） | `match/service.py` + `api/routes_match.py` + 13 测试 | 89f9930 |
| T5 | 推荐+JD 分析端点（D2 决策侧 422；B1 不落库锚定） | `api/routes_recommend.py` + `api/routes_jd.py` + 10 测试 | 2beb8f1 |
| T6 | 前端骨架 + Dashboard 六视图（SSR + 手写 SVG 雷达） | `api/routes_web.py` + `templates/` + `static/` + `test_web_pages.py`（7 测试） | 6198e73* |
| T7 | 流程页五页 + app.js（C6 localStorage 会话模型） | `templates/` 五页 + `static/app.js` + 10 测试 | 6198e73 |
| T8 | 溯源交互 + 真实 LLM 全流程走查（7 缺陷修复） | 见 §4；`PHASE_10_REVIEW.md` §4 + 结构级回归测试 | 1150586 |
| T9 | 收口：本 Review 补齐 + ROADMAP/HANDOVER 同步 + API.md 实现备注 | 本 commit |

\* T6 的 `app.py`（/static 挂载 + web_router include）与
`dashboard.html` 因 staging 遗漏未随 6198e73 入库（该提交单检出不自洽），
随 T8（1150586）补齐——详见 §4.3。

测试：**505 全绿**（Phase 9 收口 443 → +62）。

## 1. 验收核验表（对照 ROADMAP Phase 10 + 计划验收清单）

| 验收项 | 结果 | 证据 |
|---|---|---|
| 六视图数据全部来自 API（无前端硬编码数字） | ✅ | T6 渲染测试（fixture 数字必现 + 空库渲染断言）+ T9 模板抽查；走查六视图数字与 API 响应一致（§4.1 步骤 6） |
| 样本量守门在 UI 呈现（N<30 灰态占位+文案） | ✅ | T2 口径（200+insufficient 展示侧）+ T6 渲染测试 + T8 真实 global N=0 灰态走查（"样本量不足以判断趋势（N=0）"） |
| 端到端用户流程走通（PRODUCT_SPEC §3） | ✅ | T8 真实 LLM 全流程走查七步全通（§4.1：简历→画像→JD→匹配→缺口→推荐→Dashboard→global 灰态） |
| 每个数字可点击溯源（evidence_ref → JD/证据页） | ✅ | 市场页每行"查看证据" + Dashboard 缺口表技能名/热门技能条 → `/api/market/skills/{skill}/evidence` JSON 台账（job_id/标题/来源/URL/时间），T8 逐步点击验证 |
| 全量回归绿 + 六维自检 | ✅ | 505 绿（+62）；§3 |

计划 T1-T8 任务验收（各任务交付+测试数）见 §0；T9 验收 =
文档同步零偏差抽查（ROADMAP/HANDOVER/API.md 与实现一致）。

## 2. 口径裁决落地核对（C1-C7）

| # | 裁决 | 落地 |
|---|---|---|
| C1 | 10 端点 + 6 页（延后 Phase 11：contribute/import/adzuna 管道 + tasks 异步 + quality/eval 端点 + Data & Quality 页） | ✅ 10 端点全部落地；延后清单移交 §5 |
| C2 | Jinja2 SSR + 原生 JS + 手写 SVG/CSS，零框架零构建零 CDN | ✅ 无 package.json/构建步骤；雷达/条形全手写 |
| C3 | 新依赖 ADR-011 + serve 默认 127.0.0.1 | ✅ ADR-011（Flask/纯静态/Streamlit 否决理由）；`--host` 显式传参才可改绑 |
| C4 | match jd_text 模式复用 compute_match + 双模式同分锚定 | ✅ `test_dual_mode_consistency`：同 JD 双模式结果 dict 全等 |
| C5 | 无硬编码操作化为渲染测试 | ✅ fixture 数字必现 + 空库渲染断言（test_web_pages.py） |
| C6 | localStorage 会话模型（candidate_id + 最近匹配缓存） | ✅ T8 走查实证：cid=9 跨页预填、匹配概览 78.1 呈现 |
| C7 | LLM 端点 FakeLLM 三分支 + 真实 e2e 一次走查 | ✅ 全部 LLM 端点测试零真实调用；走查见 §4 |

## 3. 六维自检

### Product —— 真的解决问题吗？
六视图把"数据与决策的可视化呈现（非聊天框）"落地：每个频率数字
可点开 JD 底账、每个缺口挂着 ROI 理由、匹配分拆四维可核——用户
看到的所有数字都能回答"从哪来"。走查主流程（简历→推荐）七步无断点。

### Engineering —— 过度设计了吗？
克制点：不引入前端框架/构建链（C2）；不加"最近匹配"查询端点
（C6 用 localStorage，避免为展示加契约）；不引入连接池（D1，本地
单用户）；10 端点而非 16（C1 范围裁决，CLI 已覆盖的管道不重复暴露）。
新增代码集中在一个 `api/` 包，模板/JS 无抽象层。

### AI —— LLM 被滥用了吗？
LLM 只出现在两处受控抽取（简历/JD）+ 可选解释（explain 非默认）；
匹配分数/推荐 ROI/市场统计零 LLM（CI 静态检查红线延续）。所有 LLM
端点测试走 FakeLLM 三分支；真实 LLM 只在 T8 走查消耗一次。
explain 叙事数字不一致即拦截降级（Phase 8 机制延续，走查确认在场）。

### Data —— 数字真实吗？
走查全部数字真实：N=201/132、78.1 分、Docker 置信度 0.30（简历仅
"了解"→低置信诚实呈现）；global N=0 灰态不隐藏不编造；Adzuna 归属
在 Global 视图常驻（含灰态——数据来源声明与有无数据无关）。

### Evaluation —— 结果可验证吗？
诚实记录限制与盲区：
- **测试盲区实证**：dependency_overrides 整树替换子依赖 →
  `make_resume_extractor` 裸参数缺陷测试全绿而真实路径 422（§4.2-1）；
  已补结构级回归测试（遍历路由依赖树），但该模式提示：**依赖注入
  测试替身会掩盖真实装配错误**，真实 e2e 走查不可被测试替代
- 7 个走查缺陷中 5 个（null 渲染/分制/字段名/归属×2）属"测试断言
  未覆盖的展示细节"——渲染测试锚定结构而非逐字段文案，残余风险
  由走查兜底（一次性成本，非每回归重跑）
- T6/T7 staging 遗漏（app.py/dashboard.html 未入库）暴露"本地全绿
  ≠ 提交自洽"——工作区与 HEAD 的偏差只能靠单检出验证发现，已补齐

### Resume —— 简历价值？
可讲：FastAPI 依赖注入的真实盲区案例（测试绿但真实 422，根因是
dependency_overrides 替换粒度）；SSR vs SPA 的克制选型（零构建、
离线可用、SEO 无关场景不引入 React）；e2e 走查方法论（真实 LLM
全流程 + 截图 + 缺陷全记录——7 缺陷中 6 个是测试没覆盖的）；
契约分制/字段名这类"文档与实现漂移"的捕获方式。

## 4. 真实 LLM 全流程走查（T8，2026-09-16）

环境：真实库（china N=201 / global N=0）、真实 DeepSeek、
`uvicorn 127.0.0.1:8766`、浏览器逐页操作（表单填写 → 提交 → 结果断言）。
走查输入：合成简历（3 年 AI 应用工程师：Python/FastAPI/Flask/RAG/
LangChain/pgvector 熟练、Docker 了解）+ 合成 JD（精通 Python / 熟练 RAG /
熟悉 PostgreSQL / 了解 Docker / MCP+LangGraph 加分 / 3 年经验）。

### 4.1 步骤与结果（PRODUCT_SPEC §3 主流程）

| # | 步骤 | 结果 | 截图（本地） |
|---|---|---|---|
| 1 | /resume 粘贴简历 → 分析 | ✅ cid=9，8 技能：7 项 ★4 置信度 1.00；**Docker ★2 置信度 0.30**（简历仅写"了解"→低置信，符合证据加权预期） | t8-resume-result |
| 2 | /jd 粘贴 JD → 分析 | ✅ ai_application_dev · china；核心 16 项（Python·精通 / Docker·了解）+ 次要 3 项（pgvector / MCP / LangGraph）+ 软性 experience 3 年 + 元信息折叠（模型/版本/延迟） | t8-jd-result-fixed |
| 3 | /match（cid=9 localStorage 预填，C6 生效）+ 同 JD + explain | ✅ **78.1 分**；四维 69.0/75.0/91.3/100.0；strong 6（RAG/LangChain/PostgreSQL/pgvector/FastAPI/Flask）、weak 2（Python 等级未达标 / Docker 证据强度低——成因区分）、missing 2（Embedding/LangGraph）；LLM 解释叙事数字与 breakdown 一致 | t8-match-result |
| 4 | /recommend（14 天 / china） | ✅ roi-v1：7 项 ROI（PE 1.21 顶）+ 7 项目模板（提示词评测套件 7 天覆盖 PE+Python 顶） | t8-recommend-result |
| 5 | /market（china）+ 点击"查看证据" | ✅ 82 行频率表（Python 65.7% · N=132）；证据链接 → `/api/market/skills/Python/evidence` JSON 台账（job_id/标题/source_type/source_url/时间）逐条可溯 | t8-market |
| 6 | /?candidate_id=9 六视图 | ✅ 画像 8 卡 / 雷达 8 顶点双多边形（缺口∪画像，≤max_axes=8——D6 设计）/ 热门技能窗口标注 N=201 / 缺口 ROI 五列表 / Priority 1-3 三段式理由（含公式代入 1.21=频次×缺口÷成本）/ 匹配概览 78.1（localStorage C6 数据源） | t8-dashboard-cid9 |
| 7 | global 灰态 | ✅ "样本量不足以判断趋势（N=0）"（D5：不隐藏不编造）+ Adzuna 归属常驻（修复后）；china 视图无归属（正确） | t8-market-global-adzuna |

截图存于本地走查目录（不入库）；本表数字即验收证据。

### 4.2 走查发现的真实缺陷（7 项，全部当次修复）

| # | 缺陷 | 根因 | 修复 |
|---|---|---|---|
| 1 | 简历分析真实路径 422 `{"loc":["query","conn"]}`，浏览器报"简历分析失败：undefined"；TestClient 测试却全绿 | `make_resume_extractor(conn)` 裸参数被 FastAPI 解析为 query 参数；`dependency_overrides` 整棵替换子依赖树 → 测试路径看不到真实依赖签名 | `conn=Depends(get_conn)`；+ 结构级回归测试遍历全部路由依赖树断言无 query `conn`（test_api_app.py） |
| 2 | 失败横幅显示"undefined" | `throw new Error(X) + ""` 运算符优先级 → throw 字符串 → `err.message` undefined | 删 `+ ""`（app.js api()） |
| 3 | JD 技能卡显示字面量 `"must_have · null"` | `esc(s.intensity)` 在 intensity 可空（JD 无熟练度词）时渲染 "null" | 空则只显 importance（app.js renderJdResult） |
| 4 | 匹配总分显示 **7810.0** | overall_score 契约为 0-100 分制（§2.8），前端误 `* 100`；renderMatch 与 Dashboard 概览两处同款 | 直接 `toFixed(1)`（app.js 两处） |
| 5 | 推荐页项目区抛错，结果区整体不显示 | 前端读 `p.skills`，实际字段为 `matched_skills`/`target_skills` | 改用 `matched_skills`（与缺口交集，对应 UI_SPEC"技能覆盖"） |
| 6 | Global 灰态（N=0）时 Adzuna 归属消失 | 归属块嵌在 market.html 非灰态分支内 | 移出分支——Global 视图常驻（数据来源归属声明与有无数据无关） |
| 7 | Dashboard 市场视图完全无 Adzuna 归属 | dashboard.html 从未实现该块（UI_SPEC 全局常驻项） | Global 时显示（dashboard.html） |

缺陷 1 的方法论价值：**依赖注入测试替身会掩盖真实装配错误**——
`dependency_overrides` 替换的是整棵子依赖树，工厂函数自身的签名缺陷
（裸参数）在测试路径不可见。结构级断言（遍历路由依赖树）弥补了这一
盲区，已固化为回归测试。

### 4.3 走查附带发现的工作区问题（如实记录，随 T8 提交处置）

- **T6/T7 staging 遗漏**：`app.py`（/static 挂载 + web_router include）
  与 `templates/dashboard.html` 从未入库——6198e73 单检出时
  `create_app()` 不含页面路由且 dashboard 模板缺失（routes_web.py 已
  引用），测试无法通过；本地各轮全绿是因为工作区文件齐全、提交时漏
  add。本 T8 提交补齐两文件，自此 HEAD 恢复自洽。
- **test_api_market.py 双 BOM**（`EF BB BF` ×2）→ pytest 收集
  SyntaxError。PowerShell 写入遗留（T4 已遇一次的复发）。处置：
  `git checkout` 恢复 HEAD 版（零 diff）。

### 4.4 走查中确认符合预期的口径（非缺陷）

- Docker 置信度 0.30：简历仅"了解"→ 证据权重低，符合证据加权设计
- weak 泳道区分成因（"等级未达标" vs "证据强度低"）
- explain 叙事数字与 breakdown 一致（数字一致性拦截机制在场）
- 雷达顶点 ≤8（D6 max_axes 设计，缺口技能优先、画像纯技能补位）
- Dashboard"我的缺口"（最近推荐 priority_items）与雷达（类目 gaps
  查询）技能集不同：数据源口径不同，均为设计约定（SSR 只读不重算）

## 5. 遗留与移交（Phase 11 输入）

| 项 | 状态 | 处置 |
|---|---|---|
| CI 首跑绿验收 | ⏳ 待 push | 远端 master 现至 Phase 8（665d0db）；Phase 9/10 待用户审批后 push，push 后盯首跑 |
| E1 dispatch 验收 | ⏳ 待 push + secret | GitHub 配 `LLM_API_KEY` 后手动 dispatch 一次 |
| E3 标注双人复核 | ⏳ 用户 + 同学 | 不阻塞（Phase 8 遗留延续） |
| Adzuna 首批拉取 | ⏳ 待办 | global 市场 N=0（走查灰态即此）；250 req/day 额度节奏 |
| C1 延后端点 | Phase 11 | contribute/import/adzuna 管道端点 + tasks 异步查询 + quality/report + eval/results + Data & Quality 页 |
| compose 化连接池复议 | Phase 11 | D1 预留（本地单用户每请求连接；容器编排下再议） |

## 6. 下一步（Phase 11）

Docker + CI + Documentation（发布就绪）：compose 全栈编排、README
（Problem/Solution/Architecture/Demo/Evaluation/Limitations/Roadmap）、
文档终版与零偏差抽查、ADR 归档核对（≥5 全部已接受/已复议——现 11 个）、
自演示录制。先写 docs/plans/ 计划。
