# Phase 4 首跑真实结果（2026-09-02）

> Task 6 真实数据首跑记录：供 PHASE_4_REVIEW.md 验收表与评审文档引用。
> 环境：本地 Docker postgres 真实库，中国区 50 条 active 岗位（全部 `public_job_page` / 来源 `company_career_page` / trust_tier `tier_a`，share=1.0），数据窗口 2026-08-31 ～ 2026-09-01。
> 口径：`method_version = s11-v1`（见 `docs/STATS_METHOD.md`）。

## 1. snapshot-create（快照 #1）

命令：`skillgap snapshot-create --market china`

| 字段 | 值 |
|---|---|
| snapshot_id / evidence_ref | **1** / `snapshot#1` |
| sample_size | **50** |
| status / confidence | ok / **medium**（50 ≤ N < 200，ADR-008） |
| window | 2026-08-31 ～ 2026-09-01 |
| method_version | s11-v1 |
| source_distribution | company_career_page（tier_a）50 条，share = 1.0 |

### Top 10 技能频率（N=50）

| # | 技能 | jd_count | frequency |
|---|---|---|---|
| 1 | Python | 38 | 0.76 |
| 2 | Java | 29 | 0.58 |
| 3 | RAG | 27 | 0.54 |
| 4 | Go | 20 | 0.40 |
| 5 | Prompt Engineering | 17 | 0.34 |
| 6 | AI Coding | 16 | 0.32 |
| 7 | C++ | 15 | 0.30 |
| 8 | Function Calling | 14 | 0.28 |
| 9 | JavaScript | 11 | 0.22 |
| 10 | MySQL | 11 | 0.22 |

其余较高频：MCP 0.20 (10)、PyTorch 0.20 (10)、上下文管理/多智能体协作/Linux 各 0.18 (9)、LangChain/Redis/SQL 各 0.16 (8)、LangGraph/ReAct/SFT/LoRA/TypeScript/多模态 各 0.14 (7)……共 57 个技能入表。

## 2. skill-evidence（RAG 溯源底账）

命令：`skillgap skill-evidence --market china --skill RAG`

- `skill_id = RAG`，**jd_count = 27**，返回 27 条 `jd_refs`（job_id / title / source_type / evidence_text / source_url / collected_at）。
- `evidence_text` 回原文，样例：
  - job_id 16「AI应用开发工程师」→ evidence_text「检索增强生成」（nowcoder 来源）
  - job_id 59「平台研发-后端开发工程师（AI 应用方向）」→ evidence_text「RAG」（mihoyo 来源）
  - job_id 11「AI Agent开发工程师」→ evidence_text「RAG」（lenovo 来源）
- 27 条全部为 `source_type = public_job_page`，collected_at = 2026-09-01。

## 3. market-crosscheck（方向一致性）

命令：`skillgap market-crosscheck --market china`

- **tau = 0.1538**（Kendall tau-a，14 技能对），method = kendall_tau_a，sample_size = 50，status = ok。

| 参考技能 | 参考频率（§2.1） | 自有频率（N=50） | diff |
|---|---|---|---|
| Python | 1.00 | 0.76 | -0.24 |
| LLM 应用经验 | 0.70 | 0.12 | -0.58 |
| LangChain | 0.80 | 0.16 | -0.64 |
| RAG | 0.60 | 0.54 | -0.06 |
| Prompt Engineering | 0.45 | 0.34 | -0.11 |
| 向量数据库 | 0.40 | 0.04 | -0.36 |
| Dify | 0.35 | 0.00 | -0.35 |
| 微调/LoRA | 0.35 | 0.14 | -0.21 |
| LangGraph | 0.25 | 0.14 | -0.11 |
| FastAPI | 0.20 | 0.06 | -0.14 |
| AutoGen | 0.15 | 0.06 | -0.09 |
| Java | 0.15 | 0.58 | **+0.43** |
| MCP | 0.10 | 0.20 | **+0.10** |
| 多模态理解 | 0.10 | 0.14 | **+0.04** |

解读要点（供评审引用）：自有数据中 RAG（-0.06）、Prompt Engineering（-0.11）、LangGraph（-0.11）、AutoGen（-0.09）、多模态（+0.04）、MCP（+0.10）与参考表方向接近；偏差最大的为 LangChain（-0.64，参考表小样本对 LangChain 生态偏置）与 Java（+0.43，自采 JD 多为大厂后端/AI 应用岗，Java 出现率远高于 23 JD 小样本）。tau=0.1538 表明两套样本排序方向仅弱一致——印证 §2.1 只能作假设生成器的定位（STATS_METHOD §6 用途限定）。

## 4. stats 切片守门（agent_dev，真实数据验证）

命令：`skillgap stats --market china --category agent_dev --min-sample 30`

```json
{ "market": "china", "sample_size": 20, "status": "insufficient_sample" }
```

agent_dev 切片真实 N=20 < 30 → **拒绝出统计、不产出任何频率数字**（守门行为在真实数据上验证，与 ADR-008 / S11 一致：返回真实样本量而非编造结果）。

## 5. 结论

- 首份真实快照落地：`snapshot#1`（N=50，medium，s11-v1），market_snapshot 表从此有可追溯基线。
- 溯源闭环：top 频率技能 RAG（0.54）可逐条回查 27 条 JD 原文证据。
- 交叉对照自动化：tau + 14 技能逐条 diff 可复现（上表数字直接抄自命令 JSON 输出）。
- 守门真实生效：agent_dev 切片（N=20）被拒，未输出任何统计。
