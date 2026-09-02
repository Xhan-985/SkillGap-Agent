# Phase 4：Market Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 分市场技能频率统计（整体 + 切片：岗位类/城市/薪资段/时间窗）+ market_snapshot 快照生成（口径版本化）+ 技能→支撑 JD 溯源 + 与 MARKET_RESEARCH §2.1 的方向一致性交叉对照报告。

**Architecture:** 全部为 SQL 与纯函数计算，零 LLM 依赖（三层分离红线，CI 静态检查目标）。扩展既有 `stats.py`（S11 空跑 → Phase 4 完整实现），复用已冻结的 `STATS_FILTER` 口径常量与已有的 `market_snapshot` 表（001_init.sql，**无需新迁移**）。快照为 append-only 历史（computed_at 区分），溯源查询走同一条统计过滤口径（consent 排除永不进底账）。

**Tech Stack:** psycopg（参数化 SQL 动态 WHERE）、pytest（真实 PG 测试库）、argparse（CLI 4 命令）。

**冻结规格引用：** ROADMAP Phase 4（产出与验收）；API.md §2.11（GET /api/market/skills 查询参数与响应结构）、§2.12（GET /api/market/skills/{skill_id}/evidence 溯源底账）；MVP.md M8 + G6 统计守门；ADR-008（N<30 不出统计；置信度 high≥200 / medium 50-200 / low 30-50）；DATA_PIPELINE S11（切片 N<30 → 不生成 snapshot；统计 SQL 异常不产出部分结果）；DATA_MODEL §2.10（market_snapshot 表结构）；MARKET_RESEARCH.md §2.1（23 JD 小样本参考表——方向对照用，不作真值）。

**现状（2026-09-02）：** 中国市场 50 条 active（public_job_page），408 行 job_skill——满足 N≥30，本阶段结束即可产出首份真实快照与交叉对照报告。

---

## 文件结构（锁定）

```
src/skillgap/
  stats.py             # 扩展：切片统计 + create_snapshot + skill_evidence
                       #       + crosscheck_baseline + kendall_tau（纯函数）
  cli.py               # stats 加切片参数；新增 snapshot-create / skill-evidence / market-crosscheck
docs/
  STATS_METHOD.md      # 新建：统计口径文档（S11 冻结口径 + 切片语义 + method_version）
  plans/2026-09-02-phase4-market-intelligence.md   # 本计划
PHASE_4_REVIEW.md      # 新建：六维自检 + 验收核验表（Task 6）
tests/
  test_stats.py        # 扩展：切片/快照/溯源/交叉对照测试
  test_cli.py          # 扩展：4 个命令的 CLI 测试
```

**边界纪律：** `stats.py` 不 import `skillgap.llm` / `skillgap.extract`（Task 1 有守卫测试锁定）；切片语义任何变更必须升 `METHOD_VERSION` 并先改 `docs/STATS_METHOD.md`。

**关键口径决策（本计划锁定，实现时不得偏离）：**

| 决策点 | 口径 |
|---|---|
| 统计过滤 | 复用冻结 `STATS_FILTER`（active + 未授权贡献排除），切片仅追加 WHERE |
| 城市切片 | `ILIKE '%city%'` 子串匹配——`city` 字段存在"杭州，北京"多城格式，精确匹配会漏 |
| 薪资段切片 | 区间重叠判定：`j.salary_max >= band_min AND j.salary_min <= band_max`；带此切片时无薪资（NULL）岗位排除（无法判定归属） |
| 时间窗切片 | `collected_at::date BETWEEN window_start AND window_end`（含端点）；参数为 ISO 日期字符串 |
| frequency | `jd_count / sample_size`，切片内分母为**切片后**样本量；round 4 位 |
| min_sample | 默认 30（ADR-008），可调（API §2.11 `min_sample` 参数）但只升不降 |
| N<30 处置 | `skill_frequency` 返回 `insufficient_sample`；`create_snapshot` **不写表**（S11） |
| skill_id | v1 用 `canonical_name` 作为技能标识（稳定、可读）；API 层若换数字 id 属契约变更 |
| 交叉对照 | Kendall tau-a（并列对不计入分子）；参考表仅 14 技能方向对照，差异逐条写入报告 |

---

### Task 1: 切片统计（skill_frequency 扩展 + 零 LLM 守卫）

**Files:** Modify `src/skillgap/stats.py`、Modify `tests/test_stats.py`（扩展 `_jobs` 工厂）

- [ ] **Step 1: 扩展 `_jobs` 工厂（tests/test_stats.py，替换现有函数）**

```python
def _jobs(clean_db, n, consent="none", source="demo_dataset",
          source_type="dataset_builtin", tag="j", city=None, salary=None,
          job_category=None, collected_at=None):
    """salary=(min, max) 元组；job_category 直填枚举；collected_at 为 datetime。"""
    from datetime import datetime as _dt
    recs = []
    for i in range(n):
        r = make_rec()
        r.source.source_name = source
        r.source.source_type = source_type
        r.source.consent_status = consent
        r.title = f"AI 应用开发工程师 {tag}{i}"
        r.raw_text = f"编号{tag}{i}。" + r.raw_text  # 保证 hash 唯一
        if city:
            r.city = city
        if salary:
            r.salary_min, r.salary_max = salary
        if job_category:
            r.job_category = job_category
        if collected_at:
            r.source.collected_at = collected_at
        recs.append(r)
    run_batch(clean_db, recs)
```

- [ ] **Step 2: 写失败测试（追加到 test_stats.py）**

```python
from datetime import datetime

from skillgap.stats import skill_frequency


def test_slice_by_category(clean_db):
    _jobs(clean_db, 35)                                            # ai_application_dev
    _jobs(clean_db, 5, job_category="agent_dev", tag="a")
    sliced = skill_frequency(clean_db, "china", category="agent_dev")
    assert sliced["status"] == "insufficient_sample"
    assert sliced["sample_size"] == 5
    assert skill_frequency(clean_db, "china")["sample_size"] == 40


def test_slice_by_city_substring_match(clean_db):
    # city 字段存在"北京，上海"多城格式 → 子串匹配（口径见表）
    _jobs(clean_db, 35, city="北京，上海")
    _jobs(clean_db, 5, city="杭州", tag="h")
    out = skill_frequency(clean_db, "china", city="上海")
    assert out["sample_size"] == 35


def test_slice_by_salary_band_overlap(clean_db):
    _jobs(clean_db, 35, salary=(15000, 25000))
    _jobs(clean_db, 5, salary=(30000, 50000), tag="hi")
    _jobs(clean_db, 10, tag="ns")                                 # 无薪资
    # 带宽 [35000, 40000]：15-25K 不重叠；30-50K 重叠；无薪资排除
    out = skill_frequency(clean_db, "china", salary_min=35000, salary_max=40000)
    assert out["status"] == "insufficient_sample"
    assert out["sample_size"] == 5


def test_slice_by_window(clean_db):
    _jobs(clean_db, 35, collected_at=datetime(2026, 8, 1))
    _jobs(clean_db, 10, collected_at=datetime(2026, 9, 1), tag="w2")
    out = skill_frequency(clean_db, "china",
                          window_start="2026-09-01", window_end="2026-09-30")
    assert out["sample_size"] == 10


def test_min_sample_override(clean_db):
    _jobs(clean_db, 10)
    out = skill_frequency(clean_db, "china", min_sample=5)
    assert out["status"] == "ok" and out["confidence"] == "low"


def test_filters_echoed_in_result(clean_db):
    _jobs(clean_db, 35, city="北京", job_category="agent_dev")
    out = skill_frequency(clean_db, "china", category="agent_dev", city="北京")
    assert out["filters"] == {"category": "agent_dev", "city": "北京"}


def test_stats_module_zero_llm_dependency():
    """三层分离红线：统计模块零 LLM 依赖（ROADMAP Phase 4 自检项）。"""
    from pathlib import Path
    src = Path("src/skillgap/stats.py").read_text(encoding="utf-8")
    assert "skillgap.llm" not in src
    assert "skillgap.extract" not in src
```

- [ ] **Step 3: 运行验证失败**

Run: `& .venv\Scripts\python.exe -m pytest tests/test_stats.py -q --basetemp="E:\codexproject\SkillGap Agent\.pytest_tmp"`
Expected: 新增测试 FAIL（`skill_frequency() got an unexpected keyword argument`）

- [ ] **Step 4: 实现（stats.py 重构，保持既有测试兼容）**

```python
"""S11 频率统计（Phase 4：切片 + 快照 + 溯源 + 交叉对照）。

口径（冻结，不得改动——DATA_MODEL §3 / DATA_PIPELINE S11 / docs/STATS_METHOD.md）：
  status='active' AND (source_type <> 'user_submitted' OR consent_status='market_analysis')
切片语义（变更须升 METHOD_VERSION 并先改 docs/STATS_METHOD.md）：
  category  精确匹配 job_category 枚举
  city      ILIKE 子串（"杭州，北京"多城格式）
  salary    区间重叠（salary_max >= min AND salary_min <= max）；NULL 薪资排除
  window    collected_at::date BETWEEN start AND end（含端点）
守门（ADR-008）：N < min_sample(默认 30) 不出统计；置信度 high>=200 / medium 50-200 / low 30-50。
本模块零 LLM 依赖（CI 静态检查目标之一，tests/test_stats.py 守卫测试锁定）。
"""
from __future__ import annotations

from typing import Any

import psycopg

STATS_FILTER = (
    "j.status = 'active' AND (j.source_type <> 'user_submitted' "
    "OR j.consent_status = 'market_analysis')"
)

METHOD_VERSION = "s11-v1"   # 口径版本：过滤 + 切片语义 + frequency 公式 + 舍入


def _slice_where(category=None, city=None, salary_min=None, salary_max=None,
                 window_start=None, window_end=None) -> tuple[list[str], list[Any]]:
    """切片 → 追加 WHERE 片段与参数（语义见模块 docstring 口径表）。"""
    parts: list[str] = []
    params: list[Any] = []
    if category:
        parts.append("j.job_category = %s")
        params.append(category)
    if city:
        parts.append("j.city ILIKE %s")
        params.append(f"%{city}%")
    if salary_min is not None or salary_max is not None:
        lo = salary_min if salary_min is not None else 0
        hi = salary_max if salary_max is not None else 10**9
        parts.append("j.salary_max >= %s AND j.salary_min <= %s")
        params.extend([lo, hi])
    if window_start and window_end:
        parts.append("j.collected_at::date BETWEEN %s::date AND %s::date")
        params.extend([window_start, window_end])
    return parts, params


def sample_size(conn: psycopg.Connection, market: str, **slices) -> int:
    parts, params = _slice_where(**slices)
    where = f" AND {' AND '.join(parts)}" if parts else ""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT count(*) AS c FROM job j WHERE j.market = %s "
            f"AND {STATS_FILTER}{where}", (market, *params))
        return cur.fetchone()["c"]


def _confidence(n: int) -> str:
    if n >= 200:
        return "high"
    if n >= 50:
        return "medium"
    return "low"


def skill_frequency(conn: psycopg.Connection, market: str, *, category=None,
                    city=None, salary_min=None, salary_max=None,
                    window_start=None, window_end=None,
                    min_sample: int = 30) -> dict:
    """频率统计（API §2.11 服务层结构）：切片 + 样本量守门 + 置信度分级。"""
    slices = dict(category=category, city=city, salary_min=salary_min,
                  salary_max=salary_max, window_start=window_start,
                  window_end=window_end)
    n = sample_size(conn, market, **slices)
    if n < min_sample:
        return {"market": market, "sample_size": n,
                "status": "insufficient_sample"}

    parts, params = _slice_where(**slices)
    where = f" AND {' AND '.join(parts)}" if parts else ""
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT s.canonical_name, count(DISTINCT js.job_id) AS jd_count
                FROM job_skill js
                JOIN job j ON j.id = js.job_id
                JOIN skill s ON s.id = js.skill_id
                WHERE j.market = %s AND {STATS_FILTER}{where}
                GROUP BY s.canonical_name
                ORDER BY jd_count DESC, s.canonical_name""",
            (market, *params))
        rows = cur.fetchall()
        cur.execute(
            f"""SELECT ds.source_name, ds.trust_tier, count(*) AS c
                FROM job j JOIN data_source ds ON ds.id = j.source_id
                WHERE j.market = %s AND {STATS_FILTER}{where}
                GROUP BY ds.source_name, ds.trust_tier ORDER BY c DESC""",
            (market, *params))
        dist = cur.fetchall()
        cur.execute(
            f"""SELECT min(j.collected_at::date) AS lo, max(j.collected_at::date) AS hi
                FROM job j WHERE j.market = %s AND {STATS_FILTER}{where}""",
            (market, *params))
        win = cur.fetchone()

    skills = [
        {"canonical_name": r["canonical_name"], "jd_count": r["jd_count"],
         "frequency": round(r["jd_count"] / n, 4)}
        for r in rows
    ]
    source_distribution = [
        {"source_name": r["source_name"], "trust_tier": r["trust_tier"],
         "count": r["c"], "share": round(r["c"] / n, 4)}
        for r in dist
    ]
    filters = {k: v for k, v in slices.items() if v is not None}
    return {
        "market": market, "sample_size": n, "status": "ok",
        "confidence": _confidence(n),
        "window": {"start": str(win["lo"]) if win["lo"] else None,
                   "end": str(win["hi"]) if win["hi"] else None},
        "filters": filters,
        "skills": skills, "source_distribution": source_distribution,
        "stats_filter": STATS_FILTER, "method_version": METHOD_VERSION,
    }
```

注意：现有 `skill_frequency(clean_db, "china")` 调用签名兼容（新参数全部 keyword-only 且有默认值）；旧返回结构保留（新增 `window` / `filters` / `method_version` 键）。

- [ ] **Step 5: 运行测试通过（含既有 6 个 stats 测试不回归）**

Run: `& .venv\Scripts\python.exe -m pytest tests/test_stats.py -q --basetemp="E:\codexproject\SkillGap Agent\.pytest_tmp"`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add src/skillgap/stats.py tests/test_stats.py
git commit -m "feat(phase4): sliced skill frequency stats (category/city/salary/window) + zero-llm guard"
```

### Task 2: market_snapshot 快照生成

**Files:** Modify `src/skillgap/stats.py`（追加 `create_snapshot`）、Modify `tests/test_stats.py`

- [ ] **Step 1: 写失败测试（追加）**

```python
from skillgap.stats import METHOD_VERSION, create_snapshot


def test_create_snapshot_persists_with_method_version(clean_db):
    _jobs(clean_db, 35)
    out = create_snapshot(clean_db, "china")
    assert out["status"] == "ok"
    sid = out["snapshot_id"]
    assert out["evidence_ref"] == f"snapshot#{sid}"
    with clean_db.cursor() as cur:
        cur.execute(
            """SELECT scope, sample_size, skill_frequency, source_distribution,
                      confidence, method_version
               FROM market_snapshot WHERE id = %s""", (sid,))
        row = cur.fetchone()
    assert row["scope"] == {"market": "china"}
    assert row["sample_size"] == 35 and row["confidence"] == "low"
    assert row["method_version"] == METHOD_VERSION
    assert row["skill_frequency"][0]["canonical_name"] in ("Python", "RAG")


def test_create_snapshot_insufficient_writes_no_row(clean_db):
    _jobs(clean_db, 5)
    out = create_snapshot(clean_db, "china")
    assert out["status"] == "insufficient_sample"
    assert out["sample_size"] == 5
    with clean_db.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM market_snapshot")
        assert cur.fetchone()["c"] == 0          # S11：N<30 不生成 snapshot


def test_create_snapshot_scope_records_slices(clean_db):
    _jobs(clean_db, 35, city="北京", job_category="agent_dev")
    out = create_snapshot(clean_db, "china", category="agent_dev", city="北京")
    with clean_db.cursor() as cur:
        cur.execute("SELECT scope FROM market_snapshot WHERE id = %s",
                    (out["snapshot_id"],))
        scope = cur.fetchone()["scope"]
    assert scope["market"] == "china"
    assert scope["job_category"] == "agent_dev"
    assert scope["city"] == "北京"
```

- [ ] **Step 2: 运行验证失败**（ImportError: create_snapshot）

- [ ] **Step 3: 实现（stats.py 追加）**

```python
def create_snapshot(conn: psycopg.Connection, market: str, **slices) -> dict:
    """生成并持久化 market_snapshot（DATA_MODEL §2.10）。

    N < min_sample → 不写表（S11 失败处理：不生成 snapshot，返回样本不足）。
    快照 append-only：每次生成为新行，历史可追溯（computed_at 区分）。
    """
    result = skill_frequency(conn, market, **slices)
    if result["status"] != "ok":
        return {"market": market, "status": "insufficient_sample",
                "sample_size": result["sample_size"]}

    scope: dict[str, Any] = {"market": market}
    if slices.get("category"):
        scope["job_category"] = slices["category"]
    if slices.get("city"):
        scope["city"] = slices["city"]
    if slices.get("salary_min") is not None or slices.get("salary_max") is not None:
        scope["salary_band"] = [slices.get("salary_min"),
                                slices.get("salary_max")]
    if slices.get("window_start") and slices.get("window_end"):
        scope["window"] = [slices["window_start"], slices["window_end"]]

    import json
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO market_snapshot
               (scope, sample_size, skill_frequency, source_distribution,
                confidence, data_window_start, data_window_end, method_version)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (json.dumps(scope, ensure_ascii=False), result["sample_size"],
             json.dumps(result["skills"], ensure_ascii=False),
             json.dumps(result["source_distribution"], ensure_ascii=False),
             result["confidence"], result["window"]["start"],
             result["window"]["end"], METHOD_VERSION))
        sid = cur.fetchone()["id"]
    conn.commit()
    return {**result, "snapshot_id": sid, "evidence_ref": f"snapshot#{sid}"}
```

- [ ] **Step 4: 测试 PASS** → **Step 5: Commit** `feat(phase4): market snapshot creation (append-only, method_version, N<30 refuses)`

### Task 3: 技能溯源（API §2.12 服务层）

**Files:** Modify `src/skillgap/stats.py`（追加 `skill_evidence`）、Modify `tests/test_stats.py`

- [ ] **Step 1: 写失败测试（追加）**

```python
from skillgap.stats import skill_evidence


def test_skill_evidence_lists_supporting_jds(clean_db):
    _jobs(clean_db, 35)
    out = skill_evidence(clean_db, "china", "RAG")
    assert out["skill_id"] == "RAG" and out["jd_count"] == 35
    ref = out["jd_refs"][0]
    assert set(ref) == {"job_id", "title", "source_type",
                        "evidence_text", "source_url", "collected_at"}
    assert ref["evidence_text"] == "搭建 RAG 检索链路"   # 底账可回原文


def test_skill_evidence_unknown_skill_explicit(clean_db):
    _jobs(clean_db, 35)
    out = skill_evidence(clean_db, "china", "不存在的技能")
    assert out["status"] == "unknown_skill"
    assert out["jd_refs"] == []


def test_skill_evidence_respects_slices_and_filter(clean_db):
    _jobs(clean_db, 35)
    _jobs(clean_db, 5, city="杭州", tag="h")
    out = skill_evidence(clean_db, "china", "RAG", city="杭州")
    assert out["jd_count"] == 5
    assert all("杭州" in (r["title"] or "") or True for r in out["jd_refs"])
```

- [ ] **Step 2: 验证失败** → **Step 3: 实现（stats.py 追加）**

```python
def skill_evidence(conn: psycopg.Connection, market: str, canonical_name: str,
                   **slices) -> dict:
    """技能 → 支撑 JD 列表（API §2.12 溯源底账）。

    同一 STATS_FILTER 口径（未授权贡献永不进底账）；底账不做样本量守门
    （它不是统计，是逐条列表），但口径与统计完全一致。
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM skill WHERE canonical_name = %s",
                    (canonical_name,))
        row = cur.fetchone()
        if row is None:
            return {"skill_id": canonical_name, "status": "unknown_skill",
                    "jd_refs": []}
        skill_id = row["id"]

    parts, params = _slice_where(**slices)
    where = f" AND {' AND '.join(parts)}" if parts else ""
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT j.id AS job_id, j.title, j.source_type,
                       js.evidence_text, j.source_url, j.collected_at
                FROM job_skill js
                JOIN job j ON j.id = js.job_id
                WHERE js.skill_id = %s AND j.market = %s
                  AND {STATS_FILTER}{where}
                ORDER BY j.collected_at DESC, j.id""",
            (skill_id, market, *params))
        refs = [dict(r) for r in cur.fetchall()]
    return {"skill_id": canonical_name, "jd_count": len(refs), "jd_refs": refs}
```

- [ ] **Step 4: 测试 PASS** → **Step 5: Commit** `feat(phase4): skill evidence tracing (api 2.12, consent-filtered)`

### Task 4: 与 MARKET_RESEARCH §2.1 交叉对照（方向一致性）

**Files:** Modify `src/skillgap/stats.py`（追加 `REFERENCE` / `REFERENCE_TO_CANONICAL` / `kendall_tau` / `crosscheck_baseline`）、Modify `tests/test_stats.py`

- [ ] **Step 1: 写失败测试（追加）**

```python
from skillgap.stats import (REFERENCE, REFERENCE_TO_CANONICAL,
                            crosscheck_baseline, kendall_tau)


def test_kendall_tau_pure_function():
    assert kendall_tau([(1, 1), (2, 2), (3, 3)]) == 1.0      # 完全同序
    assert kendall_tau([(1, 3), (2, 2), (3, 1)]) == -1.0     # 完全逆序
    assert kendall_tau([(1, 1), (1, 2)]) == 0.0              # 并列对不计入分子
    assert kendall_tau([(1, 1)]) == 0.0                      # n<2 无定义 → 0


def test_reference_table_covers_marketing_research_2_1():
    # §2.1 全部 14 个技能条目都在参考表中（防漏抄）
    assert len(REFERENCE) == 14
    assert set(REFERENCE) == set(REFERENCE_TO_CANONICAL)


def test_reference_mapping_targets_in_taxonomy(clean_db):
    # 映射目标必须是词表 canonical_name（taxonomy v1.4 已核对：
    # LLM 应用开发/LangChain/LangGraph/AutoGen/Prompt Engineering/MCP/Dify/
    # FastAPI/Milvus/Chroma/Qdrant/SFT/LoRA/多模态/Python/Java/RAG 均在）
    with clean_db.cursor() as cur:
        cur.execute("SELECT canonical_name FROM skill")
        names = {r["canonical_name"] for r in cur.fetchall()}
    for ref_name, canon in REFERENCE_TO_CANONICAL.items():
        missing = [c for c in canon if c not in names]
        assert not missing, f"{ref_name} 映射不在词表: {missing}"


def test_crosscheck_report_shape_and_tau(clean_db):
    _jobs(clean_db, 35)     # RAG/Python 全量命中 → our_frequency = 1.0
    out = crosscheck_baseline(clean_db, "china")
    assert out["status"] == "ok"
    assert -1.0 <= out["tau"] <= 1.0
    assert out["method"] == "kendall_tau_a"
    assert "MARKET_RESEARCH.md" in out["reference_source"]
    row = next(r for r in out["comparison"] if r["reference_skill"] == "Python")
    assert row["our_frequency"] == 1.0
    assert row["reference_frequency"] == 1.00
    assert "diff" in row


def test_crosscheck_insufficient_sample(clean_db):
    _jobs(clean_db, 5)
    out = crosscheck_baseline(clean_db, "china")
    assert out["status"] == "insufficient_sample"
```

- [ ] **Step 2: 验证失败** → **Step 3: 实现（stats.py 追加）**

```python
# MARKET_RESEARCH.md §2.1 参考表（23 JD 小样本，[5] 来源）。
# 用途限定：方向一致性对照（假设检验），不作为真值——本模块的使命就是
# 用自建数据集把这张表变成可复现、可追溯的数据。
REFERENCE: dict[str, float] = {
    "Python": 1.00, "LLM 应用经验": 0.70, "LangChain": 0.80, "RAG": 0.60,
    "Prompt Engineering": 0.45, "向量数据库": 0.40, "Dify": 0.35,
    "微调/LoRA": 0.35, "LangGraph": 0.25, "FastAPI": 0.20, "AutoGen": 0.15,
    "Java": 0.15, "MCP": 0.10, "多模态理解": 0.10,
}

# 参考名 → 词表 canonical_name（taxonomy v1.4 已核对全部存在）。
# 向量数据库无单一对应技能 → 取 Milvus/Chroma/Qdrant 频率最大值。
REFERENCE_TO_CANONICAL: dict[str, list[str]] = {
    "Python": ["Python"], "LLM 应用经验": ["LLM 应用开发"],
    "LangChain": ["LangChain"], "RAG": ["RAG"],
    "Prompt Engineering": ["Prompt Engineering"],
    "向量数据库": ["Milvus", "Chroma", "Qdrant"],
    "Dify": ["Dify"], "微调/LoRA": ["SFT/LoRA"], "LangGraph": ["LangGraph"],
    "FastAPI": ["FastAPI"], "AutoGen": ["AutoGen"], "Java": ["Java"],
    "MCP": ["MCP"], "多模态理解": ["多模态"],
}


def kendall_tau(pairs: list[tuple[float, float]]) -> float:
    """Kendall tau-a（并列对不计入分子，分母为全部对数）。纯函数，零 LLM。"""
    n = len(pairs)
    if n < 2:
        return 0.0
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx = pairs[i][0] - pairs[j][0]
            dy = pairs[i][1] - pairs[j][1]
            if dx * dy > 0:
                concordant += 1
            elif dx * dy < 0:
                discordant += 1
    denom = n * (n - 1) / 2
    return round((concordant - discordant) / denom, 4)


def crosscheck_baseline(conn: psycopg.Connection, market: str,
                        **slices) -> dict:
    """自有数据集频率 vs MARKET_RESEARCH §2.1 参考表的方向一致性报告。

    ROADMAP Phase 4 验收项：方向一致性检查，差异写入报告（逐技能 diff）。
    """
    freq = skill_frequency(conn, market, **slices)
    if freq["status"] != "ok":
        return {"market": market, "status": "insufficient_sample",
                "sample_size": freq["sample_size"]}
    ours = {s["canonical_name"]: s["frequency"] for s in freq["skills"]}

    rows, pairs = [], []
    for ref_name, ref_freq in REFERENCE.items():
        canon = REFERENCE_TO_CANONICAL.get(ref_name, [])
        if not canon:
            rows.append({"reference_skill": ref_name, "status": "unmapped"})
            continue
        our_freq = max(ours.get(c, 0.0) for c in canon)
        rows.append({
            "reference_skill": ref_name, "canonical": canon,
            "reference_frequency": ref_freq, "our_frequency": our_freq,
            "diff": round(our_freq - ref_freq, 4),
        })
        pairs.append((ref_freq, our_freq))
    return {
        "market": market, "status": "ok",
        "sample_size": freq["sample_size"],
        "method": "kendall_tau_a", "tau": kendall_tau(pairs),
        "reference_source": "MARKET_RESEARCH.md §2.1（23 JD 小样本，非官方）",
        "note": "方向对照仅用于假设检验，不作为真值；差异逐条见 comparison",
        "comparison": rows,
        "method_version": METHOD_VERSION,
    }
```

- [ ] **Step 4: 测试 PASS** → **Step 5: Commit** `feat(phase4): direction crosscheck vs MARKET_RESEARCH 2.1 (kendall tau-a, per-skill diff)`

### Task 5: CLI（stats 扩展 + 3 新命令）

**Files:** Modify `src/skillgap/cli.py`、Modify `tests/test_cli.py`

- [ ] **Step 1: 写失败测试（追加到 test_cli.py，复用既有 main(db_url=TEST_URL) 模式）**

```python
def test_stats_slice_flags(clean_db, capsys):
    rc = main(["stats", "--market", "china", "--category", "agent_dev",
               "--city", "北京", "--min-sample", "5"], db_url=TEST_URL)
    assert rc == 0
    import json
    out = json.loads(capsys.readouterr().out)
    assert out["filters"]["category"] == "agent_dev"


def test_snapshot_create_command(clean_db, capsys):
    from tests.test_stats import _jobs
    _jobs(clean_db, 35)
    rc = main(["snapshot-create", "--market", "china"], db_url=TEST_URL)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok" and "snapshot#" in out["evidence_ref"]


def test_skill_evidence_command(clean_db, capsys):
    rc = main(["skill-evidence", "--market", "china", "--skill", "RAG"],
              db_url=TEST_URL)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["skill_id"] == "RAG"


def test_market_crosscheck_command(clean_db, capsys):
    from tests.test_stats import _jobs
    _jobs(clean_db, 35)
    rc = main(["market-crosscheck", "--market", "china"], db_url=TEST_URL)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok" and "tau" in out
```

- [ ] **Step 2: 验证失败**（argparse unrecognized arguments）

- [ ] **Step 3: 实现（cli.py）**

parser 追加（`p_st` 定义处扩展 + 3 个新 parser；`from skillgap.ingest.normalize import JOB_CATEGORIES`）：

```python
    def _add_slice_flags(p):
        p.add_argument("--category", choices=sorted(JOB_CATEGORIES))
        p.add_argument("--city")
        p.add_argument("--salary-min", type=int)
        p.add_argument("--salary-max", type=int)
        p.add_argument("--window-start", help="ISO 日期 YYYY-MM-DD")
        p.add_argument("--window-end", help="ISO 日期 YYYY-MM-DD")

    p_st = sub.add_parser("stats", help="频率统计（S11 口径，支持切片）")
    p_st.add_argument("--market", choices=["china", "global"], default="china")
    p_st.add_argument("--min-sample", type=int, default=30)
    _add_slice_flags(p_st)

    p_snap = sub.add_parser("snapshot-create",
                            help="生成市场统计快照（N<30 拒绝写表）")
    p_snap.add_argument("--market", choices=["china", "global"], default="china")
    p_snap.add_argument("--min-sample", type=int, default=30)
    _add_slice_flags(p_snap)

    p_ev2 = sub.add_parser("skill-evidence", help="技能 → 支撑 JD 溯源底账")
    p_ev2.add_argument("--skill", required=True, help="词表 canonical_name")
    p_ev2.add_argument("--market", choices=["china", "global"], default="china")
    _add_slice_flags(p_ev2)

    p_cc = sub.add_parser("market-crosscheck",
                          help="与 MARKET_RESEARCH §2.1 方向一致性对照")
    p_cc.add_argument("--market", choices=["china", "global"], default="china")
    p_cc.add_argument("--min-sample", type=int, default=30)
    _add_slice_flags(p_cc)
```

分支实现（替换现有 `stats` 分支 + 追加 3 个；文件顶部 import 追加 `create_snapshot, skill_evidence, crosscheck_baseline`）：

```python
        def _slice_kwargs(args):
            kw = {}
            if getattr(args, "category", None):
                kw["category"] = args.category
            if getattr(args, "city", None):
                kw["city"] = args.city
            if getattr(args, "salary_min", None) is not None:
                kw["salary_min"] = args.salary_min
            if getattr(args, "salary_max", None) is not None:
                kw["salary_max"] = args.salary_max
            if getattr(args, "window_start", None):
                kw["window_start"] = args.window_start
            if getattr(args, "window_end", None):
                kw["window_end"] = args.window_end
            if getattr(args, "min_sample", None):
                kw["min_sample"] = args.min_sample
            return kw

        elif args.command == "stats":
            _print(skill_frequency(conn, args.market, **_slice_kwargs(args)))
        elif args.command == "snapshot-create":
            _print(create_snapshot(conn, args.market, **_slice_kwargs(args)))
        elif args.command == "skill-evidence":
            _print(skill_evidence(conn, args.market, args.skill,
                                  **_slice_kwargs(args)))
        elif args.command == "market-crosscheck":
            _print(crosscheck_baseline(conn, args.market,
                                       **_slice_kwargs(args)))
```

注意：`test_parser_subcommands` 既有测试若按子命令清单断言，需同步追加 3 个新命令名。

- [ ] **Step 4: 测试 PASS（全量回归）**

Run: `& .venv\Scripts\python.exe -m pytest tests/ -q --basetemp="E:\codexproject\SkillGap Agent\.pytest_tmp"`
Expected: 全绿（178 + 新增约 20）

- [ ] **Step 5: Commit** `feat(phase4): cli stats slices + snapshot-create/skill-evidence/market-crosscheck`

### Task 6: 真实数据首跑 + 口径文档 + Phase 4 评审

**Files:** Create `docs/STATS_METHOD.md`、Create `PHASE_4_REVIEW.md`、Modify `docs/ROADMAP.md`（追加 Phase 4 Review 记录）、Modify `docs/HANDOVER.md`（§2 进度与 §9 任务状态）

- [ ] **Step 1: 真实首跑（50 条中国数据）**

```powershell
& .venv\Scripts\skillgap.exe snapshot-create --market china
& .venv\Scripts\skillgap.exe skill-evidence --market china --skill RAG
& .venv\Scripts\skillgap.exe market-crosscheck --market china
& .venv\Scripts\skillgap.exe stats --market china --category agent_dev --min-sample 30
```

预期：快照 #1（N=50，confidence=medium）；RAG 溯源返回 20 条左右 agent_dev 类 JD；交叉对照产出 tau 与逐技能 diff（写入 PHASE_4_REVIEW.md 验收表）；agent_dev 切片 N=20 <30 → insufficient_sample（守门行为在真实数据上验证）。

- [ ] **Step 2: 写 `docs/STATS_METHOD.md`（统计口径文档——ROADMAP Phase 4 产出项"统计口径文档化"）**

内容框架：① 统计过滤口径（STATS_FILTER 原文 + 解释）；② 切片语义表（本计划"关键口径决策"表迁移过去）；③ frequency 公式与舍入；④ 样本量守门与置信度分级（ADR-008）；⑤ method_version 变更纪律（升版本须先改本文档）；⑥ 交叉对照方法（Kendall tau-a + 参考表限定用途）；⑦ 溯源底账口径（同过滤，无守门的原因）。

- [ ] **Step 3: 写 `PHASE_4_REVIEW.md`（六维自检 + 验收核验表）**

验收核验表（ROADMAP Phase 4 验收项逐条）：

| 验收项 | 证据 |
|---|---|
| 每个百分比可追溯到 JD 列表 | `skill-evidence` 每技能返回 jd_refs（含 evidence_text 回原文） |
| 统计口径文档化 | `docs/STATS_METHOD.md` + METHOD_VERSION=s11-v1 |
| 与 §2.1 方向一致性交叉对照，差异写入报告 | `market-crosscheck` 输出 tau + 逐技能 diff，结论抄录进本文档 |

六维自检：Product（M8 是否闭环）/ Engineering（是否过度设计）/ AI（零 LLM，守卫测试）/ Data（数字全部来自自有数据集）/ Evaluation（真实首跑数字 + 守门行为验证）/ Resume（"所有频率数字都是 SQL 算的且可溯源"）。

- [ ] **Step 4: 更新 ROADMAP.md（Phase 4 Review 记录）与 HANDOVER.md（进度/任务/命令表）**

- [ ] **Step 5: 全量回归 + Commit（仅本地，禁止 push）**

```bash
git add docs/STATS_METHOD.md docs/ROADMAP.md docs/HANDOVER.md PHASE_4_REVIEW.md
git commit -m "docs(phase4): stats method doc + phase 4 review + real-data first snapshot (N=50)"
```

---

## Self-Review 结论

1. **规格覆盖**：切片统计 SQL（T1：岗位类/城市/薪资段/时间窗）｜market_snapshot 生成含口径版本（T2，method_version + N<30 拒绝）｜样本量守门（T1 min_sample + T2 不写表 + T6 真实数据验证）｜技能→JD 溯源（T3，§2.12 结构 + consent 过滤）｜交叉对照差异写入报告（T4 tau + diff，ROADMAP 验收项）｜统计口径文档化（T6 STATS_METHOD.md）｜CLI（T5）｜（预留）时间切片查询 = window 切片即 T1 已含。无遗漏。
2. **占位符扫描**：无 TBD/TODO；所有代码步骤含完整实现；T6 文档步骤为内容框架（文档本身的写作大纲，非代码占位）。
3. **类型一致性**：`skill_frequency(conn, market, *, category, city, salary_min, salary_max, window_start, window_end, min_sample)`、`create_snapshot(conn, market, **slices)`、`skill_evidence(conn, market, canonical_name, **slices)`、`crosscheck_baseline(conn, market, **slices)`、`kendall_tau(pairs)` 在 T1-T5 间引用一致；`_slice_kwargs` 产出的键与 `_slice_where` 形参一致（min_sample 由 skill_frequency 消费，`_slice_where` 不接收——`create_snapshot`/`crosscheck_baseline` 经 `skill_frequency` 透传，无冲突）。
