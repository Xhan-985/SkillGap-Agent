# 证据权重规则表（Candidate Profile）

> 版本：conf-v1 ｜ 冻结于 2026-09-03 ｜ 公式实现：`src/skillgap/profile/confidence.py`（纯函数，单测全覆盖）

## 1. 证据分级与权重

| 证据类型 | 判定 | weight | 示例 |
|---|---|---|---|
| `project_detail` | 具体技术栈 + 做法/量化结果 | **1.0** | "pgvector + Hybrid Search + RRF + Rerank 检索链路，召回率提升 18%" |
| `project_desc` | 项目提及该技能但缺细节 | **0.6** | "参与公司知识库 RAG 项目" |
| `bare_claim` | 无项目支撑的裸声明 | **0.3** | "熟悉 RAG" |
| `manual` | 用户手动勾选（显式确认） | **1.0** | 手动勾选面板选中 "Python" |

权重值域与 `candidate_evidence.weight` 的 DB CHECK（`IN (1.0, 0.6, 0.3)`）严格一致。

## 2. confidence 公式

```
confidence = min(1.0, Σᵢ w₍ᵢ₎ × 0.5^(i-1))
```

- `w₍ᵢ₎`：该技能的证据权重，**降序排列**后计（顺序无关性可单测验证）
- `0.5^(i-1)`：**次数衰减** γ=0.5——第 2 条证据贡献减半、第 3 条 quarter，防证据堆刷分
- 空证据列表 → 0.0；结果 round 4 位小数

**confidence 是纯函数规则计算，非 LLM 输出**（ROADMAP Phase 5 自检红线；守卫测试锁定 `confidence.py` 零 LLM 依赖）。

## 3. 逐例演算（单测 `tests/test_profile_confidence.py` 对应）

| 证据权重组合 | 演算 | confidence |
|---|---|---|
| `[1.0]`（单条 project_detail） | 1.0 | **1.0** |
| `[0.6]`（单条 project_desc） | 0.6 | **0.6** |
| `[0.3]`（单条 bare_claim——"熟悉 RAG"） | 0.3 | **0.3** |
| `[1.0]`（manual 手动勾选） | 1.0 | **1.0** |
| `[0.3, 0.3]`（两条裸声明） | 0.3 + 0.15 | **0.45** |
| `[0.3, 0.3, 0.3]` | 0.3 + 0.15 + 0.075 | **0.525** |
| `[1.0, 0.3]`（细节 + 声明） | 1.0 + 0.15 → 截断 | **1.0** |
| `[0.6, 0.6]` | 0.6 + 0.3 | **0.9** |
| `[0.6, 0.6, 0.6]` | 0.6 + 0.3 + 0.15 = 1.05 → 截断 | **1.0** |
| `[]`（无证据） | — | **0.0** |

## 4. 语义要点（决策记录 D1/D3/D5）

- **level 与 confidence 正交**：`candidate_skill.level`（1-5 星）= 能力宣称强度（LLM 从证据推断，手动勾选可覆盖）；confidence = 系统对该技能的相信程度。"声明是 3 星，但系统只有 0.3 相信"是预期产品叙事（声明 vs 证明）。
- **重分析为替换式**（D1）：同一 candidate 重新分析简历 → 删除其全部 `source_type='resume_text'` 技能行后插入新结果（陈旧证据不跨版本累积）；`manual` 行永不删除，与新简历冲突时跳过插入并显式提示。
- **手动勾选整行覆盖**（D5）：`add_manual_skill` 将已有行（含 resume 来源）替换为 manual 行（confidence=1.0），代表用户最新意图。
- **置信度如何进入下游**：Match 公式中 `conf_factor = 0.5 + 0.5 × confidence`（DATA_MODEL §4）；confidence 不直接进 gap（gap 是星级差）。
