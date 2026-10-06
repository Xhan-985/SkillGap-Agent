# SkillGap Agent

证据化技能决策系统：从中文 AI 岗位 JD 出发，输出可溯源的市场技能频率、个人技能画像、Skill Gap 量化、可解释匹配分与 ROI 学习建议。每个数字可回溯到 JD 原文证据。

## Problem

- 中文 AI 岗位的技能需求数字（"RAG 岗位占比多少""Agent 岗位要什么技术栈"）没有合法的自动化数据源，公开频率数据不存在；
- 现有求职/简历匹配工具给出黑盒匹配分，无法回答"这个分怎么算的、我该先补什么"；
- 通用 LLM 问答可以泛泛而谈，但给不出带样本量与原文证据的统计口径。

## Solution

一条可溯源的技能决策闭环：

```
JD 采集（三通道，无爬虫红线）→ LLM 结构化抽取（带原文证据，Schema 校验）
→ 市场频率统计（纯 SQL）→ 证据化个人画像（置信度 = 证据加权纯函数）
→ Skill Gap 量化 → 可解释匹配（四维拆解 + 三列泳道）
→ ROI 优先级建议（Demand×Gap÷Cost）+ LangGraph Agent 叙事（数值零权限）
```

核心设计纪律是三层分离：**Deterministic Layer**（统计/评分/ROI 全部 SQL 与纯函数，CI 静态检查零 LLM）/ **LLM Layer**（只做抽取与解释，输出必过 Schema 校验，失败明示不降级）/ **Evidence Layer**（每个数值携带 evidence_ref，可点开 JD 原文底账）。样本量 <30 时系统拒绝出数（ADR-008）。

## Architecture

模块化单体（Modular Monolith），单人可维护、clone 即可运行：

- **FastAPI**：13 个契约端点 + Jinja2 SSR 六页 Dashboard（原生 JS，零框架零构建零 CDN）
- **PostgreSQL 16 + pgvector**：结构化 JD/技能关系 + 证据向量检索（bge-m3 1024 维 + HNSW）
- **LangGraph**：单 Career Planner Agent（4 节点状态机，解释层旁路——数值路径零 LLM 权限）
- **DeepSeek**（OpenAI-compatible，httpx 直连）：抽取与解释的唯一智能来源

架构图、有界上下文与技术栈决策见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)；12 份决策记录见 [docs/adr/](docs/adr/)。

## Demo

▶ **60 秒演示视频**：全流程走查——简历分析 → 匹配 → ROI 推荐 → 市场统计 → 六视图总览。

<!-- ▼ 视频内嵌位置：在 GitHub 网页编辑器里把 skillgap-explainer.mp4 拖到本行下方，
     GitHub 会自动上传并生成内嵌播放器（手机、电脑都能直接播放）。
     上传完成后，可删掉这条注释与下面的"直接下载观看"一行。 -->

- 直接下载观看：[skillgap-explainer.mp4](https://github.com/Xhan-985/SkillGap-Agent/releases/download/v1.0.0/skillgap-explainer.mp4)（10 MB，Release v1.0.0 托管）
- 视频用 Remotion 制作，成片经 GitHub Release 分发

前置：Docker。三条命令起全栈（postgres + app；entrypoint 自动迁移、种子、起服）：

```bash
git clone https://github.com/Xhan-985/SkillGap-Agent.git
cd SkillGap-Agent
cp .env.example .env        # LLM_API_KEY 等按需填；不填服务可起，LLM 功能明示不可用
docker compose up -d        # → http://127.0.0.1:8000
```

验证：`curl http://127.0.0.1:8000/api/health` 返回 `{"status":"ok","db":true,...}`；浏览器打开 http://127.0.0.1:8000 进入六页 Dashboard（画像/JD 分析/匹配/推荐/市场/总览）。

可选——导入演示数据（批次 CSV 随仓库分发，可重放）：

```bash
docker compose exec app skillgap import --file data/batch_1.csv
```

空库时市场与统计页呈灰态（`insufficient: true`），属预期的诚实降级而非故障。

## Evaluation

三层评测 + 门禁（指标定义、阈值、方差与分诊见 [docs/EVALUATION.md](docs/EVALUATION.md)）：

| 评测 | 对象 | 规模 | 最新指标（2026-09-22 库） | verdict |
|---|---|---|---|---|
| E1 技能抽取 | JD → 技能（LLM 为被测件） | N=53 | F1=0.8644 / recall=0.8173 / evidence_rate=1.0 | warn |
| E2 岗位匹配 | 匹配分 vs 人工标注（零 LLM） | N=25 | Spearman ρ=0.8277 / MAE=9.67 / Jaccard=0.967 | pass |
| E3 学习推荐 | Top-5 排序 vs 标注相关性 | N=5 | nDCG@5=0.6497 / hit_rate@3=1.0 | pass |

评测集规模只支撑版本间相对回归比较，不支持绝对能力宣称。`eval-gate` 门禁在真实缺陷下完成过一次真实拦截（评测集引用漂移 → ρ 0.8277→0.445 → exit 1）。

## Limitations

如实声明（与代码行为一致）：

- **全球市场无数据**：Adzuna 通道代码就绪但尚未拉取，global 市场 N=0，统计页灰态明示（`insufficient: true`）；
- **单用户无鉴权**：服务默认绑 127.0.0.1，任何公网部署前必须先加认证与限流（API.md §0 部署红线）；
- **评测集规模边界**：E1 N=53 / E2 N=25 / E3 N=5，结论限于相对回归比较；
- **中国数据集规模**：202 条 active 岗位（单人分 3 批人工收集，来源与批次见 [docs/DATA.md](docs/DATA.md)），切片统计在 N<30 时拒绝出数；
- **简历输入为纯文本**：PDF 解析后置；画像 level 推断无独立评测集背书（手动勾选兜底）。

## Roadmap

Phase 0-10 已完成：市场研究 → 需求冻结/架构 → 数据管道 → JD 抽取 → 市场统计 → 画像 → Gap → 匹配 → 推荐 + LangGraph Agent → 三层评测 + CI → FastAPI Dashboard。Phase 11（Docker + CI + 文档，发布就绪）收尾中。后续候选：贡献端点与异步任务（API.md §2.2，T4）、Data & Quality 页（T5）、Adzuna 全球数据首拉、E3 标注双人复核。详见 [docs/ROADMAP.md](docs/ROADMAP.md)。
