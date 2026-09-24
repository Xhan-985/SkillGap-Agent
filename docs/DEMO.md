# DEMO —— 自演示脚本（从 clone 到浏览器全流程）

> 用途：在全新环境用**三条命令**起全栈，并按脚本走完浏览器端到端流程（步骤 + 命令 + 预期输出）。
> 录制说明（C5 裁决）：本脚本入库，录屏产物为个人资产不入库；OBS / Win+G 均可，建议 1080p 逐节录制。
> 走查实录（含缺陷记录）见 `PHASE_11_REVIEW.md` §4，与本脚本步骤一一对应。

---

## 0. 前置条件

| 项 | 说明 |
|---|---|
| Docker Desktop | 已启动（Windows/macOS/Linux 均可；首次构建需联网拉取 `python:3.12-slim` 与 pip 依赖） |
| LLM key（可选） | `LLM_API_KEY`（DeepSeek，https://platform.deepseek.com ）。不填：服务照常起，LLM 功能页明示"未配置"；填了：走查第 2/3 步为真实抽取 |
| 端口 | 本机 5432 / 6379 / 8000 空闲（已有本机 PostgreSQL 等服务时先停，或改 compose 端口映射） |

## 1. 三条命令起全栈

```bash
git clone https://github.com/Xhan-985/SkillGap-Agent.git
cd SkillGap-Agent
cp .env.example .env        # 编辑 .env 填入 LLM_API_KEY（可选）
docker compose up -d
```

> `docker compose up -d` 首次运行包含镜像构建（pip 安装依赖，约 2-5 分钟）；随后自动完成迁移 + 种子 + 起服。

**预期输出**（`docker compose logs app` 可见 entrypoint 三段日志）：

```
[entrypoint] db-upgrade：应用未执行的迁移...
[entrypoint] seed：词表 v1 + 来源注册表建档（幂等）...
[entrypoint] serve：启动 API / Dashboard...
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**健康验证**：

```bash
curl http://127.0.0.1:8000/api/health
```

```json
{"status":"ok","db":true,"llm":"configured"}
```

（未填 key 时 `llm` 为 `"unconfigured"`——服务仍 ok，属预期而非故障。）

**幂等重启验证（可选）**：`docker compose restart app` → 上述三段日志重复出现且迁移数为 0、seed 不重复插入，health 依旧 ok——重启安全（ADR-012 D3）。

## 2. 可选：导入演示数据

空库时市场/统计页呈灰态（`insufficient: true`，样本量守门 ADR-008）——这本身是预期的诚实降级演示。要演示有数据的市场视图，导入随仓库分发的批次 CSV：

```bash
docker compose exec app skillgap import --file data/batch_1.csv
```

**预期输出**（空库首导，50 行批次）：

```json
{"total": 50, "inserted": 50, "duplicates": 0, "rejected": 0, "quarantined": 0, "errors": []}
```

批次 2/3 同理（`data/batch_2.csv` / `data/batch_3.csv`）；批次历史与口径见 [DATA.md](DATA.md)。

## 3. 浏览器全流程（七页 + 贡献闭环）

打开 http://127.0.0.1:8000 ——导航七页：画像 / JD 分析 / 匹配 / 推荐 / 市场 / 总览 / 数据与质量。

> 以下样例为**合成数据**（非真实个人/公司信息；JD 含手机号用于演示 PII 脱敏）。
> 预期值标注"参考"处依赖 LLM 当次抽取，数值会有合理波动，形态与字段应一致。

### 3.1 /resume —— 简历 → 证据化画像

粘贴合成简历并提交：

```
李明 ｜ AI 应用开发工程师 ｜ 3 年经验
- 熟练使用 Python 进行后端与服务开发（FastAPI / Flask）
- 熟练构建 RAG 系统：LangChain + pgvector 检索、Hybrid Search 与 Rerank
- 熟悉 PostgreSQL 数据建模与性能调优
- 了解 Docker 容器化部署，写过 Dockerfile 与 compose 编排
- 本科 · 软件工程；英语 CET-6
```

**预期**：返回 candidate_id（右上角会话标识，localStorage 保持）；技能列表带置信度——
参考形态：RAG / Python / FastAPI / LangChain / PostgreSQL / pgvector 等熟练项置信度 ≥0.9，
**Docker 仅"了解"→ 置信度低（~0.3）**（证据加权纯函数的诚实呈现，非缺陷）。

### 3.2 /jd —— JD 分析 + 匿名贡献（T4 闭环，重点）

在"岗位标题"输入框填写 `AI 应用开发工程师`（**对贡献必填**——为空时贡献走质检隔离 quarantine 明示，与 CLI `--title` 必填同口径），粘贴合成 JD 并提交：

```
【AI 应用开发工程师】某科技公司 · 上海
职责：基于 RAG 与 Agent 构建企业知识库问答产品；设计实现 LLM 应用后端（Python）。
要求：精通 Python，3 年以上后端经验；熟练掌握 RAG 全链路（Embedding/向量检索/Rerank）；
熟悉 PostgreSQL 及 pgvector；了解 Docker；加分：MCP、LangGraph。
联系方式：13800138000（HR 直招）
```

**预期（分析）**：岗位类别 `ai_application_dev` · 市场 china；核心技能（Python·精通 / RAG·熟练）+
次要技能（PostgreSQL / Docker / pgvector / MCP / LangGraph）+ 软性要求（经验 3 年）+ 元信息折叠（模型/版本/延迟）。
默认**不落库**（无状态即时计算，B1 口径）。

**预期（贡献）**：分析成功后页面下方出现"匿名贡献到市场数据集"区（默认隐藏，opt-in）：

1. 勾选"我同意匿名贡献此 JD"（默认未勾，直接点提交会被拦截提示）；
2. 点"提交贡献" → `202 + task_id`，前端轮询任务状态；
3. 完成后展示：**岗位 #N · 技能抽取 done** + **PII 替换摘要**（`phone: 1` ——JD 里的手机号已被规则替换）+
   **deletion_code（红色大字号，一次性展示，请立即保存）**；
4. 刷新后再查同一任务（`GET /api/tasks/{id}`）→ `deletion_code: null`——已展示过即作废（D5 一次性语义）。

（可选——诚实失败演示：标题留空提交贡献 → 任务 `failed` + 红横幅明示 quarantine 原因（`empty_title`），
原文进人工复核队列不入统计——失败不静默，数据治理口径可见。）

### 3.3 /match —— 可解释匹配

candidate_id 已由会话预填；粘贴同一 JD → 提交。

**预期**：总分（参考 ~78/100，随抽取波动）+ 四维拆解（coverage / importance_coverage / evidence_quality / experience_relevance）
+ 三列泳道（强项 / 弱项 / 缺口——Docker 低置信入弱项，MCP/LangGraph 无证据入缺口）。分数计算零 LLM（CI 静态检查保证）。

### 3.4 /recommend —— ROI 建议

**预期**：按 `需求频率 × 缺口 ÷ 学习成本` 排序的建议列表（如 LangGraph / MCP 置顶），
每条含市场需求数据来源与样本量；无数据维度不出数。

### 3.5 /market —— 市场频率 + 溯源

**预期**：技能频率表（N=导入样本数；未导入则灰态 `insufficient: true`）；
每行"查看证据"可点开台账（job_id / 标题 / 来源 / 采集时间）——**每个数字可回溯到 JD 底账**。
Global 切片恒灰态 N=0（Adzuna 未首拉，如实呈现）。

### 3.6 /dashboard —— 总览

**预期**：画像雷达图 + 缺口表 + 热门技能条（数据全部来自 API，无前端硬编码数字）；
六视图数字与各页一致。

### 3.7 /quality —— 数据与质量（T5 新增，重点）

**预期**：
- **来源分布 Tier 表**（SSR 直出：Tier A Adzuna / Tier B 用户贡献 / Tier C 批次导入，含条款核查日期）；
- **五指标卡**：重复率 / 缺失率 / 无效率 / 抽取覆盖率 / PII 扫描（规则版本 + 命中数）；
- **评测历史表**：E1/E2/E3 各版本主指标 + verdict + 基线对比（空库时为空表占位，属预期）。

### 3.8 删除贡献（走查收尾，§2.14 闭环）

用 3.2 保存的 deletion_code 删除刚才的贡献（岗位回到贡献前状态）：

```bash
curl -X DELETE http://127.0.0.1:8000/api/contributions/{deletion_code}
# 预期：204 No Content；重复删除同一 code → 404（一次性）；错误 code 不区分"无效/已删"（防探测）
```

## 4. 收尾与边界

```bash
docker compose down        # 停栈（数据卷保留，下次 up 数据还在）
docker compose down -v     # 彻底清除（含数据卷）——演示机回收用
```

- 服务只绑 `127.0.0.1`（compose 端口映射强制，API.md §0 部署红线）；公网部署前必须先加认证与限流；
- LLM 只出现在抽取与可选解释，统计/评分/推荐路径零 LLM；
- 所有市场数字受 N<30 守门（ADR-008），灰态即诚实降级，不是故障。

## 5. 常见问题

| 现象 | 原因与处置 |
|---|---|
| `docker compose up` 端口冲突 | 本机已有 PostgreSQL/Redis 占用 5432/6379——停用本机服务或改 compose 端口映射 |
| health 返回 `db:false` | postgres 容器未就绪（healthcheck 10×5s），等几秒重试 |
| LLM 页面报 502 | `LLM_API_KEY` 未填/失效——`.env` 补齐后 `docker compose up -d` 重建 |
| 统计页灰态 | 样本量 <30 守门或空库——导入 §2 演示数据，或按灰态口径演示诚实降级 |
| Windows 下脚本换行问题 | 仓库 `.gitattributes` 已强制 `*.sh eol=lf`，正常 clone 不会触发；若手工复制文件需检查 LF |
