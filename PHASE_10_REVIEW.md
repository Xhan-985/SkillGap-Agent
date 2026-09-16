# Phase 10 Review —— Dashboard / API / 前端 验收与六维自检

> 阶段：FastAPI 10 端点 + Jinja2 SSR 六页 + 原生 JS 前端 + 真实 LLM e2e 走查。
> 计划：`docs/plans/2026-09-08-phase10-dashboard.md`（口径裁决 C1-C7 +
> 冻结决策 D1-D10）。
>
> **本文件随 T8 提交先落 §4（真实走查记录）**；§0 交付物清单 / §1 验收
> 核验表 / §2-§3 六维自检 / §5 遗留移交由 T9 收口补齐。

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
