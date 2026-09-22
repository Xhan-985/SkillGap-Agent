# DEVELOPMENT —— 开发环境与工程指南

## 1. 环境搭建

- Python ≥3.11（`pyproject.toml` requires-python；本机 .venv 为 3.12，CI 跑 3.11）
- Docker Desktop（PostgreSQL 依赖；Windows 下须手动启动）
- 安装：`pip install -e ".[dev]"`——运行依赖 8 项（psycopg / httpx / pydantic / pydantic-settings / langgraph / fastapi / uvicorn / jinja2），dev 仅 pytest，零冗余依赖（每项对应 ADR）
- `.env`：`cp .env.example .env`——`DATABASE_URL` / `TEST_DATABASE_URL` 必填；`LLM_API_KEY`（DeepSeek，抽取/评测/画像用）按需；`ADZUNA_*`（全球拉取）；`EMBEDDING_API_KEY`（RAG 向量）

两种运行方式：

```bash
# A. 全栈容器（推荐，发布形态）：app 服务 entrypoint 自动 db-upgrade + seed + uvicorn
docker compose up -d                 # → http://127.0.0.1:8000（仅本机，部署红线）

# B. 本机开发：只起数据库，代码跑在 .venv
docker compose up -d postgres
skillgap db-upgrade && skillgap seed
skillgap serve                       # 默认 127.0.0.1:8000
```

## 2. 测试（514 项，需真实 PostgreSQL）

```powershell
& .venv\Scripts\python.exe -m pytest tests/ -q --basetemp=".pytest_tmp"
```

- conftest 起独立 `skillgap_test` 库并自动应用全部 migrations；每测试事务隔离
- **本机必须带 `--basetemp`**：默认临时目录权限被拒（WinError 5，已知坑）；系统 Python 无 pytest，必须用 .venv 解释器
- ⚠️ **假绿警告**：Docker 未启动时 PG 依赖测试静默 skip 且 exit 0——跑完看 skipped 计数，不信裸 exit 0
- 分层：纯函数守卫测试（scoring / gapcalc / roi / confidence 锁定公式）→ API TestClient 契约测试（fixture 用 `(client, conn)` 元组模式）→ 评测器全链路 fixture（FakeLLM 零费用）→ 劣化演练（改坏权重 → gate block 的反向对照）

## 3. CI（`.github/workflows/ci.yml`）

| job | 触发 | 内容 |
|---|---|---|
| test | PR + push master | pgvector/pgvector:pg16 服务容器 + 迁移预检（ensure_database + db-upgrade）+ pytest 全量 |
| docker | PR + push master | 仅构建应用镜像不推送（验证 Dockerfile 可构建；与 test 并行） |
| e1 | 仅 workflow_dispatch 手动 | E1 真实 LLM 跑分（需 `secrets.LLM_API_KEY`，缺席 skip 有提示；key 泄露/费用/flaky 不进 PR） |

- workflow 文件**必须在远端才生效**——本地改动看不到执行；首跑绿：run 35686447520（test success，e1 skipped 属正常）
- 全量基线评测（E2/E3 × 真实市场数据）留本地：eval_run 是 source of truth，gate/report 离线读库

## 4. 数据库迁移

- `migrations/*.sql` 顺序编号（001 init / 002 batch error_count / 003 llm_cache+eval_run / 004 rag_evidence；005 task 表为 Phase 11 T4 计划）
- 纪律：**幂等可重跑**（IF NOT EXISTS）；新迁移只增表/增列，不改既有表语义
- 应用：`skillgap db-upgrade`；测试库由 conftest 自动应用全量
- 词表 / 来源注册表种子：`skillgap seed`（幂等）

## 5. 工程纪律（全局红线）

1. **三层分离**：确定性层（统计/评分/ROI）禁止 import LLM——守卫测试 + CI 静态检查双闸；LLM 输出必过 Pydantic Schema 校验，失败明示不降级
2. Prompt 任何变更必须跑 `eval-e1` 回归（F1 历史可比）；公式变更必须升版本（scoring_version / gap_version / formula_version 随 eval_run 落库）
3. 新增依赖先补 ADR（范例：fastapi → ADR-011）；范围变更先改 MVP.md/ADR 再动代码
4. git：push 需用户明确批准（审批制）；commit 单行超详细中文；`tests/test_prompt.py` 与个人数据文件保持不入库
5. 文档不得出现反向工程相关内容

## 6. Windows 已知坑

| 坑 | 处置 |
|---|---|
| pytest 默认临时目录权限被拒 | 必须 `--basetemp` 指向项目内目录（§2） |
| PowerShell 无 bash heredoc | git commit 多行信息用单行 `-m` 或写临时文件 `git commit -F` |
| PowerShell 写文件留 BOM（曾致测试文件 SyntaxError） | 代码文件一律用编辑工具写，不用 `Set-Content` |
| `*.sh` 被 git 转 CRLF → 容器内 `\r` 报错 | `.gitattributes` 强制 `*.sh text eol=lf` |
| 本地代理下线 push 失败 | 直连单次覆盖：`git -c http.proxy= -c https.proxy= push origin master` |
| Shell 跨命令不保持目录 | 每条命令显式指定工作目录（cwd），不依赖上一条的 cd |
| 破坏性 docker 命令（down -v / volume rm）曾删开发卷 | 执行前核验项目名/卷归属；临时栈用 `-p` 隔离；**永不**对开发项目 down -v（2026-09-22 事故教训） |
