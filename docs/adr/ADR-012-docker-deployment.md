# ADR-012：应用如何容器化部署（Docker Compose 全栈）？

状态：**已接受** ｜ 日期：2026-09-18 ｜ Phase 11 Docker + CI + Documentation

## Context

Phase 11 目标是发布就绪：全新环境 clone 后按 README **三条命令内跑通**（ROADMAP 验收原文）。现状：postgres 已在 compose（pgvector/pgvector:pg16），但 app 跑在宿主机 `.venv`——演示者必须先装 Python 3.12 + `pip install -e ".[dev]"`，命令数远超三条。

两个前置决策点：① Phase 10 D1 预留的"compose 长驻进程是否引入连接池"复议；② 异步任务（API.md §2.2 contribute 契约 202 + task_id）的实现载体（见 DECISION_LOG D-2026-09-18-19 C2，DB 任务表 + BackgroundTasks，不在本 ADR 展开）。

约束：API.md §0 部署红线——MVP 无鉴权仅限本地单用户，任何容器化方案不得默认对外网开放。

## Options

| 选项 | Pros | Cons |
|---|---|---|
| **A. 全栈容器化**（Dockerfile app 镜像 + compose postgres+app，entrypoint 自动 migrate+seed+serve） | 演示者零本机 Python 依赖；三条命令可达；环境一致性强（CI docker build 同一 Dockerfile 验证） | 镜像构建时长进 CI；entrypoint 脚本有 CRLF/BOM 平台坑；容器内调试隔一层 |
| B. 维持现状（仅 postgres 容器，app 宿主机 venv） | 零新文件；开发迭代最快 | README 达不成三条命令验收；换机/换账号演示成本高（HANDOVER §13 迁移痛点） |
| C. 云部署（K8s/Fly.io 等） | 真实生产形态 | 超出 MVP 范围：无鉴权服务上云=安全红线；API.md §0 明确本地单用户；维护成本与单人项目不匹配 |

## Decision

**选项 A，边界如下**：

1. **Dockerfile**：单阶段 `python:3.12-slim`，非 root 用户，`pip install .`（api package-data 随包，Phase 10 D7 已备）；不追求多阶段瘦身（无编译链依赖，YAGNI）。
2. **entrypoint**：`db-upgrade` → `seed` → `uvicorn`，全幂等（重启安全）；迁移失败即退（fail-fast，不带病起服）。`*.sh` 强制 LF（`.gitattributes`）。
3. **compose**：`app` depends_on postgres healthy；`environment` 显式注入 `DATABASE_URL=postgresql://skillgap:skillgap@postgres:5432/skillgap`（服务名连接串优先于 env_file——**用户 .env 无须为容器改任何配置**）；端口 `127.0.0.1:8000:8000`（部署红线延续，compose 也不默认对外）。
4. **连接池复议（关闭 Phase 10 D1 挂起项）：维持无池**。compose 不改变部署语义（仍本地单用户，只是免去本机装 PG）；每请求连接在容器网络下 ~ms 级开销；引入 psycopg_pool 须回归全部端点测试，收益低于成本。
5. **redis 维持现状**：不接入 app（LLM 缓存走 DB llm_cache，ADR 既定），compose 中保留供后续评估。

## Consequences

- 正面：README Demo 段三条命令成立（clone / cp .env / compose up）；宿主机 venv 路径（HANDOVER §4）完全不受影响——两条部署路径并存，容器化是叠加不是替换；CI docker build job 与 test 并行，镜像烂构建早发现
- 负面：CI 增一个 job（~1-2min，并行不阻塞）；Windows 下 Docker Desktop 须手动启动（已知坑，T8 前置检查）；entrypoint 脚本平台坑需 .gitattributes 兜底
- 诚实边界：compose 全栈 e2e 不进 CI（时长 + Docker-in-Docker 复杂度），留 T8 手动走查——CI 只保证"镜像可构建"，不保证"compose 起来全绿"

## Reversibility

撤销成本：**低**。删 Dockerfile + entrypoint + compose app service 即回到现状（postgres-only compose）；app 代码零改动（连接串经环境注入，config.py 既有机制）。
