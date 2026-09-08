# ADR-011：为什么引入 FastAPI（Web/API 层）？

状态：**已接受** ｜ 日期：2026-09-08 ｜ Phase 10 Dashboard

## Context

Phase 10 要交付 Dashboard 六视图 + 端到端用户流程（PRODUCT_SPEC §3：简历粘贴 → 画像 → JD 粘贴 → 匹配 → 缺口 → 推荐 → Dashboard）。项目至今 CLI-only，但 API.md 契约（Phase 1 冻结，16 端点）从未落地。UI_SPEC 设计原则"服务端渲染或轻前端均可"+ ROADMAP 自检"无花哨前端框架依赖"。

服务层已齐备（stats/profile/match/gap/recommend/analyzer，443 测试绿）——缺的只是一层 HTTP 装配：请求校验 → 调 service → 契约裁剪 → 统一错误体。

## Options

| 选项 | Pros | Cons |
|---|---|---|
| **FastAPI + Jinja2 SSR** | 原生 pydantic v2（项目已用 ≥2.7，请求/响应模型零新概念）；TestClient 复用既有 httpx（零新测试依赖）；SSR 与 /api/* 同 app；类型化契约与 API.md 八要素对齐；async 就绪（未来 LLM 流式） | 新依赖 3 个（fastapi/uvicorn/jinja2）；模板逻辑在 Python 侧 |
| Flask + Jinja2 | 更轻；SSR 传统 | 请求校验手写或加 marshmallow（又新依赖）；无原生类型化契约；TestClient 走 werkzeug（新测试栈） |
| 纯静态前端 + 现有 CLI | 零后端改动 | 16 端点契约无处安放；LLM key 须下发前端（安全红线）；e2e 流程断裂 |
| Streamlit / Gradio | 快速原型 | UI_SPEC 明令"不是聊天框"且验收要求数据全部来自 API 可溯源——这类框架数字绑定黑盒，与"每个数字可点击溯源"冲突 |

## Decision

**FastAPI ≥0.115 + uvicorn + jinja2。** `create_app()` 工厂；API 层零计算（只组装既有 service 输出，响应按 API.md 契约裁剪——超集字段剥离）；SSR 页面路由与 /api/* 同 app；`skillgap serve` 默认绑定 127.0.0.1（API.md §0 部署红线：MVP 无鉴权仅限本地）。

## Consequences

- 正面：契约（pydantic schema）即测试锚定；TestClient 与既有 pytest/fixtures/FakeLLM 全兼容；SSR 保前端零框架零构建零 CDN（离线可用）
- 负面：+3 依赖（uvicorn/jinja2 属 fastapi 生态标准伴生）；接受——均为纯 Python 无编译链，Windows 本地零摩擦

## Reversibility

撤销成本：**低**。API 层只装配不计算，service 层零感知；撤除 = 删 api/ 包 + 卸依赖，CLI 能力不受影响。
