# Phase 3：JD Analyzer + Skill Extraction（含 E1 评测）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 粘贴 JD → LLM Structured Output 抽取技能（带证据、可校验、可评测），E1 基线 F1 ≥ 0.75。

**Architecture:** LLM Gateway（Provider 抽象 + DeepSeek 单实现 + DB 缓存 + 重试）作为防腐层；抽取层实现 Phase 2 冻结的 `SkillExtractor` 协议；E1 评测器独立消费抽取输出（只读，LLM 不参与指标计算）。三层分离纪律：LLM 只抽取，不做统计、不改数值。

**Tech Stack:** httpx（OpenAI-compatible chat/completions，不加 openai SDK）、Pydantic、PostgreSQL（migration 003：llm_cache + eval_run）、pytest + httpx.MockTransport。

**冻结规格引用：** ADR-009（LLM Structured Output + alias 归一 + 证据可溯校验 + 重试 ≤2 次后明示失败）；API.md §2.1（/api/jd/analyze 响应结构与 LLM_EXTRACTION_FAILED 语义）；EVALUATION_PLAN.md §2（E1 指标与阈值：F1 Pass ≥0.85 / Warn 0.75-0.85 / Block <0.75；证据可溯率 100% 硬要求）；ARCHITECTURE.md（LLM Gateway = 防腐层）。

**用户决策（2026-08-31）：** DeepSeek（deepseek-chat）｜种子标注集先行（20-30 条，真实收集后增量替换至 50-100）｜LLM 缓存用 DB 表（不用 Redis）。

---

## 文件结构（锁定）

```
src/skillgap/
  llm/
    __init__.py          # 导出
    provider.py          # LLMProvider 协议 + LLMResponse + OpenAICompatibleProvider（httpx）
    gateway.py           # LLMGateway：缓存→调用（重试）→缓存；PROMPT 无关，纯 messages 层
  extract/
    __init__.py
    prompt.py            # PROMPT_VERSION + SYSTEM_PROMPT + few-shot 示例（与评测集分离）
    llm_extractor.py     # LLMSkillExtractor（SkillExtractor 协议）：JSON 解析+校验+证据定位+重试
    analyzer.py          # analyze_jd()：确定性字段（normalize.py）+ LLM 抽取 → API §2.1 结构
  eval/
    __init__.py
    seed.py              # 种子标注集 20 条 → evaluation_sample 入库（幂等）
    e1.py                # E1 评测器：跑分 + P/R/F1 + 证据可溯率 + 阈值 + eval_run 入库
data/eval/e1_seed_v1.json   # 种子标注集数据（dataset_version=e1_seed_v1）
migrations/003_llm_eval.sql # llm_cache + eval_run 表
src/skillgap/cli.py     # + jd-analyze / eval-e1 / backfill-extraction 子命令
tests/
  test_llm_provider.py  test_llm_gateway.py  test_llm_extractor.py
  test_analyzer.py  test_e1.py  (+conftest DATA_TABLES 更新)
```

**边界纪律**：`llm/` 不知道抽取 Schema；`extract/` 不知道 HTTP 细节；`eval/` 只读消费。依赖方向：analyzer → extractor → gateway → provider。

---

### Task 1: 配置 + migration 003 + conftest

**Files:** Modify `src/skillgap/config.py`、Create `migrations/003_llm_eval.sql`、Modify `tests/conftest.py`、Modify `src/skillgap/llm/__init__.py`（空包标记）

- [ ] **Step 1: migration 003**

```sql
-- 003: Phase 3 —— LLM 响应缓存（ADR-009：content_hash 缓存缓解成本）+ 评测回归历史（EVALUATION_PLAN §6）
CREATE TABLE IF NOT EXISTS llm_cache (
    cache_key      TEXT PRIMARY KEY,           -- sha256(model + messages canonical)
    response       JSONB NOT NULL,
    provider       TEXT NOT NULL,
    model          TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS eval_run (
    id             SERIAL PRIMARY KEY,
    eval_type      TEXT NOT NULL CHECK (eval_type IN ('skill_extraction','matching','recommendation','data_quality')),
    dataset_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model          TEXT NOT NULL,
    metrics        JSONB NOT NULL,             -- 全部指标 + 版本三元组 + 环境
    sample_size    INT NOT NULL,
    verdict        TEXT NOT NULL CHECK (verdict IN ('pass','warn','block')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- [ ] **Step 2: config.py 追加（Settings 类内）**

```python
    # Phase 3: LLM Gateway（OpenAI-compatible 单实现——用户决策 DeepSeek）
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_timeout: float = 60.0     # API.md §0：LLM 相关 60s
    llm_max_retries: int = 2      # ADR-009：失败重试 ≤2 次后明示
```

- [ ] **Step 3: conftest.py DATA_TABLES 追加 `"llm_cache", "eval_run",`（放在 evaluation_sample 之前）**
- [ ] **Step 4: `pytest -q` 全量通过（003 迁移被 db.upgrade 自动应用）**
- [ ] **Step 5: Commit** `feat(phase3): llm/eval schema (llm_cache, eval_run) + deepseek config`

### Task 2: LLM Provider（OpenAI-compatible，httpx 直调）

**Files:** Create `src/skillgap/llm/provider.py`、Create `src/skillgap/llm/__init__.py`、Test `tests/test_llm_provider.py`

- [ ] **Step 1: 失败测试**

```python
import httpx
import pytest
from skillgap.llm.provider import LLMResponse, OpenAICompatibleProvider

OK_BODY = {"choices": [{"message": {"content": '{"skills": []}'}}],
           "usage": {"total_tokens": 120}}

def _provider(handler):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatibleProvider(base_url="https://llm.test", api_key="k",
                                    model="m", http=http, timeout=5.0)

def test_chat_returns_response_and_sends_bearer():
    seen = {}
    def handler(req: httpx.Request):
        seen["auth"] = req.headers["Authorization"]
        seen["url"] = str(req.url)
        return httpx.Response(200, json=OK_BODY)
    resp = _provider(handler).chat(
        messages=[{"role": "user", "content": "hi"}], response_json=True)
    assert isinstance(resp, LLMResponse)
    assert resp.content == '{"skills": []}'
    assert resp.total_tokens == 120
    assert seen["auth"] == "Bearer k"
    assert "chat/completions" in seen["url"]

def test_429_500_retry_then_success(monkeypatch):
    from skillgap.llm import provider as m
    monkeypatch.setattr(m, "_sleep", lambda s: None)
    n = {"i": 0}
    def handler(req):
        n["i"] += 1
        return httpx.Response(429) if n["i"] == 1 else httpx.Response(200, json=OK_BODY)
    resp = _provider(handler).chat([{"role": "user", "content": "x"}])
    assert resp.content == '{"skills": []}' and n["i"] == 2

def test_persistent_error_raises_llmerror(monkeypatch):
    from skillgap.llm import provider as m
    monkeypatch.setattr(m, "_sleep", lambda s: None)
    def handler(req):
        return httpx.Response(500)
    with pytest.raises(m.LLMError, match="LLM 调用失败"):
        _provider(handler).chat([{"role": "user", "content": "x"}])

def test_response_json_flag_forces_json_object():
    seen = {}
    def handler(req: httpx.Request):
        import json as j
        seen["body"] = j.loads(req.content)
        return httpx.Response(200, json=OK_BODY)
    _provider(handler).chat([{"role": "user", "content": "x"}], response_json=True)
    assert seen["body"]["response_format"] == {"type": "json_object"}
```

- [ ] **Step 2: 验证失败**（`pytest tests/test_llm_provider.py -v` → ImportError/ModuleNotFoundError）
- [ ] **Step 3: 实现**

```python
"""LLM Provider 抽象 + OpenAI-compatible 单实现（httpx 直调，零 SDK 依赖）。

Gateway 的底层：只管 HTTP（鉴权/重试/超时），不管业务 Schema。
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

_sleep = time.sleep  # 测试可注入
RETRYABLE_STATUS = (408, 429, 500, 502, 503, 504)


class LLMError(RuntimeError):
    """LLM 调用层错误（网络/HTTP/超时）——与抽取层校验失败区分。"""


@dataclass
class LLMResponse:
    content: str
    total_tokens: int = 0
    model: str = ""


class LLMProvider(Protocol := None):  # 用 typing.Protocol 见下方正式版
    ...
```

正式版以 `typing.Protocol` 定义：

```python
from typing import Protocol

class LLMProvider(Protocol):
    def chat(self, messages: list[dict], response_json: bool = False) -> LLMResponse: ...


class OpenAICompatibleProvider:
    def __init__(self, base_url: str, api_key: str, model: str,
                 http: httpx.Client | None = None, timeout: float = 60.0,
                 max_retries: int = 2):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.http = http or httpx.Client(timeout=timeout)
        self.max_retries = max_retries

    def chat(self, messages: list[dict], response_json: bool = False) -> LLMResponse:
        payload: dict = {"model": self.model, "messages": messages,
                         "temperature": 0.0}   # 抽取任务要求确定性
        if response_json:
            payload["response_format"] = {"type": "json_object"}
        last: str = ""
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.http.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            except httpx.HTTPError as e:
                last = f"网络错误: {e}"
                if attempt < self.max_retries:
                    _sleep(2 ** attempt)
                    continue
                raise LLMError(f"LLM 调用失败（重试 {self.max_retries} 次）: {last}")
            if resp.status_code in RETRYABLE_STATUS:
                last = f"HTTP {resp.status_code}"
                delay = resp.headers.get("Retry-After")
                _sleep(min(float(delay), 30) if delay else 2 ** attempt)
                continue
            if resp.status_code != 200:
                raise LLMError(f"LLM HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            try:
                return LLMResponse(
                    content=data["choices"][0]["message"]["content"],
                    total_tokens=(data.get("usage") or {}).get("total_tokens", 0),
                    model=data.get("model", self.model),
                )
            except (KeyError, IndexError, TypeError) as e:
                raise LLMError(f"LLM 响应结构异常: {e}")
        raise LLMError(f"LLM 调用失败（重试 {self.max_retries} 次）: {last}")
```

- [ ] **Step 4: `pytest tests/test_llm_provider.py -v` 全 PASS**
- [ ] **Step 5: Commit** `feat(phase3): openai-compatible provider with retry (httpx, no sdk)`

### Task 3: LLM Gateway（DB 缓存 + 调用编排）

**Files:** Create `src/skillgap/llm/gateway.py`、Test `tests/test_llm_gateway.py`

- [ ] **Step 1: 失败测试**

```python
import httpx
import psycopg
import pytest
from skillgap.llm.gateway import LLMGateway, cache_key

OK = {"choices": [{"message": {"content": '{"ok": 1}'}}],
      "usage": {"total_tokens": 10}}
MSGS = [{"role": "user", "content": "extract: 你好"}]


def _gateway(clean_db, handler, model="m"):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    from skillgap.llm.provider import OpenAICompatibleProvider
    p = OpenAICompatibleProvider("https://llm.test", "k", model, http=http)
    return LLMGateway(clean_db, provider=p, prompt_version="v1")


def test_cache_key_deterministic_and_model_scoped():
    k1 = cache_key("m", MSGS)
    k2 = cache_key("m", list(MSGS))
    k3 = cache_key("other", MSGS)
    assert k1 == k2 and k1 != k3 and len(k1) == 64


def test_first_call_hits_provider_and_caches(clean_db):
    calls = {"n": 0}
    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, json=OK)
    gw = _gateway(clean_db, handler)
    r1 = gw.chat(MSGS, response_json=True)
    r2 = gw.chat(MSGS, response_json=True)
    assert r1.content == r2.content == '{"ok": 1}'
    assert calls["n"] == 1          # 第二次命中缓存
    with clean_db.cursor() as cur:
        cur.execute("SELECT provider, model, prompt_version FROM llm_cache")
        row = cur.fetchone()
    assert row["model"] == "m" and row["prompt_version"] == "v1"


def test_cached_for_model_version(clean_db):
    """模型不同 → 缓存不串。"""
    def handler(req):
        return httpx.Response(200, json=OK)
    gw_m = _gateway(clean_db, handler, model="m")
    gw_m.chat(MSGS)
    gw_m2 = _gateway(clean_db, handler, model="m2")
    gw_m2.chat(MSGS)   # 不同 cache_key，不抛错
    with clean_db.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM llm_cache")
        assert cur.fetchone()["c"] == 2


def test_provider_error_not_cached(clean_db):
    from skillgap.llm.provider import LLMError
    n = {"i": 0}
    def handler(req):
        n["i"] += 1
        if n["i"] <= 3:
            return httpx.Response(500)
        return httpx.Response(200, json=OK)
    from skillgap.llm import provider as pm
    import skillgap.llm.gateway as gm
    gm._provider_sleep = lambda s: None   # gateway 测试不等待
    gw = _gateway(clean_db, handler)
    with pytest.raises(LLMError):
        gw.chat(MSGS)
    with clean_db.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM llm_cache")
        assert cur.fetchone()["c"] == 0
```

（注：provider 重试 sleep 由 Task 2 的 `provider._sleep` 控制，monkeypatch 即可；上面 `gm._provider_sleep` 一行删除，改为 `monkeypatch.setattr(pm, "_sleep", lambda s: None)` 的 fixture。）

- [ ] **Step 2: 验证失败** → **Step 3: 实现**

```python
"""LLM Gateway：缓存查询 → provider 调用（重试）→ 缓存写入（防腐层）。

对上层暴露 chat(messages)：消息级 API；业务 Schema 校验在 extract 层。
缓存键 = sha256(model + 规范化 messages)——同模型同输入幂等（ADR-009 成本缓解）。
"""
from __future__ import annotations

import hashlib
import json

import psycopg

from skillgap.llm.provider import LLMProvider, LLMResponse


def _canonical_messages(messages: list[dict]) -> str:
    return json.dumps(messages, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def cache_key(model: str, messages: list[dict]) -> str:
    return hashlib.sha256(
        (model + "|" + _canonical_messages(messages)).encode("utf-8")).hexdigest()


class LLMGateway:
    def __init__(self, conn: psycopg.Connection, provider: LLMProvider,
                 prompt_version: str):
        self.conn = conn
        self.provider = provider
        self.prompt_version = prompt_version

    def chat(self, messages: list[dict], response_json: bool = False) -> LLMResponse:
        key = cache_key(self.provider.model, messages)
        row = self._cache_get(key)
        if row is not None:
            return LLMResponse(content=row["response"]["content"],
                               total_tokens=row["response"].get("total_tokens", 0),
                               model=self.provider.model)
        resp = self.provider.chat(messages, response_json=response_json)
        self._cache_put(key, resp)
        return resp

    def _cache_get(self, key: str) -> dict | None:
        with self.conn.cursor() as cur:
            cur.execute("SELECT response FROM llm_cache WHERE cache_key = %s", (key,))
            r = cur.fetchone()
        return r

    def _cache_put(self, key: str, resp: LLMResponse) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO llm_cache (cache_key, response, provider, model, prompt_version)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (cache_key) DO NOTHING""",
                (key, json.dumps({"content": resp.content,
                                  "total_tokens": resp.total_tokens}),
                 type(self.provider).__name__, self.provider.model,
                 self.prompt_version))
        self.conn.commit()
```

- [ ] **Step 4: 测试 PASS** → **Step 5: Commit** `feat(phase3): llm gateway with db response cache`

### Task 4: 抽取 Prompt v1 + JDExtraction Schema

**Files:** Create `src/skillgap/extract/__init__.py`、`src/skillgap/extract/prompt.py`、Modify `src/skillgap/models.py`（追加 JDExtraction）、Test `tests/test_prompt.py`

- [ ] **Step 1: models.py 追加**

```python
SoftReqTypeEnum = Literal["experience", "education", "language"]


class SoftRequirement(BaseModel):
    type: SoftReqTypeEnum
    value: str
    evidence_text: str


class JDExtraction(BaseModel):
    """LLM 抽取输出契约（ADR-009）。证据可溯由 extract 层程序校验。"""
    skills: list[SkillAnnotation]
    soft_requirements: list[SoftRequirement] = Field(default_factory=list)
```

- [ ] **Step 2: prompt.py 实现（含版本常量与 few-shot——与评测集严格分离）**

```python
"""抽取 Prompt v1（版本化管理——EVALUATION_PLAN §6）。

防污染纪律（E1 §2.1）：few-shot 示例不得取自评测集；本文件示例为自构演示文本。
"""
PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """你是招聘 JD 的技能抽取器。任务：从 JD 原文中抽取技术技能与软性要求，输出严格 JSON。

规则：
1. skills 数组：每个技能含 raw_name（原文表述，不改写）、importance（must_have=硬性要求/nice_to_have=加分项）、intensity（精通/熟练/熟悉/了解，原文无程度词则省略）、evidence_text（支持该技能的 JD 原文连续片段，10-40 字，禁止拼凑与改写——系统会做字符串定位校验）。
2. 只抽技术技能（语言/框架/工具/平台/方法论）。不抽：学历、年限、软素质（沟通能力等）、公司福利。
3. soft_requirements 数组：experience（年限）/education（学历）/language（语言要求），同样必须附原文证据片段。
4. 不确定的技能宁可不抽（漏报代价高于误报的领域除外——本任务要求召回优先，倾向抽取所有明确提及的技能）。
5. 输出仅一个 JSON 对象：{"skills": [...], "soft_requirements": [...]}，无其他文本。

示例输入（演示文本，非评测数据）：
"岗位：后端开发。要求：3 年以上 Python 经验，熟悉 Django 与 PostgreSQL，了解 Docker 部署优先。本科及以上。"
示例输出：
{"skills": [{"raw_name": "Python", "importance": "must_have", "intensity": "熟悉", "evidence_text": "3 年以上 Python 经验"}, {"raw_name": "Django", "importance": "must_have", "evidence_text": "熟悉 Django"}, {"raw_name": "PostgreSQL", "importance": "must_have", "evidence_text": "熟悉 Django 与 PostgreSQL"}, {"raw_name": "Docker", "importance": "nice_to_have", "intensity": "了解", "evidence_text": "了解 Docker 部署优先"}], "soft_requirements": [{"type": "experience", "value": "3 年以上", "evidence_text": "3 年以上 Python 经验"}, {"type": "education", "value": "本科", "evidence_text": "本科及以上"}]}"""


def extraction_messages(jd_text: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"抽取以下 JD：\n\n{jd_text}"},
    ]
```

- [ ] **Step 3: 测试**

```python
from skillgap.extract.prompt import PROMPT_VERSION, extraction_messages


def test_prompt_version_frozen():
    assert PROMPT_VERSION == "v1"


def test_messages_wrap_jd_text():
    msgs = extraction_messages("岗位职责：负责 RAG 开发")
    assert msgs[0]["role"] == "system"
    assert "JD 技能抽取器" in msgs[0]["content"]
    assert "负责 RAG 开发" in msgs[1]["content"]
```

- [ ] **Step 4: 测试 PASS** → **Step 5: Commit** `feat(phase3): extraction prompt v1 + JDExtraction contract`

### Task 5: LLMSkillExtractor（协议实现 + 证据校验 + 明示失败）

**Files:** Create `src/skillgap/extract/llm_extractor.py`、Test `tests/test_llm_extractor.py`

- [ ] **Step 1: 失败测试**

```python
import httpx
import pytest
from skillgap.llm.provider import OpenAICompatibleProvider
from skillgap.llm.gateway import LLMGateway
from skillgap.extract.llm_extractor import LLMSkillExtractor, ExtractionFailed


def _extractor(clean_db, content: str):
    def handler(req):
        return httpx.Response(200, json={"choices": [
            {"message": {"content": content}}], "usage": {"total_tokens": 50}})
    http = httpx.Client(transport=httpx.MockTransport(handler))
    p = OpenAICompatibleProvider("https://t", "k", "m", http=http)
    return LLMSkillExtractor(LLMGateway(clean_db, provider=p, prompt_version="v1"))


GOOD = """{"skills": [{"raw_name": "RAG", "importance": "must_have",
 "intensity": "熟悉", "evidence_text": "搭建 RAG 检索链路"}],
 "soft_requirements": [{"type": "experience", "value": "1-3年",
 "evidence_text": "1-3年大模型应用开发经验"}]}"""
JD = "岗位职责：搭建 RAG 检索链路。要求：1-3年大模型应用开发经验。"


def test_extract_ok(clean_db):
    anns = _extractor(clean_db, GOOD).extract(JD)
    assert anns[0].raw_name == "RAG" and anns[0].importance == "must_have"


def test_markdown_fenced_json_tolerated(clean_db):
    anns = _extractor(clean_db, f"```json\n{GOOD}\n```").extract(JD)
    assert anns[0].raw_name == "RAG"


def test_evidence_not_locatable_raises(clean_db):
    BAD = GOOD.replace("搭建 RAG 检索链路", "原文不存在的片段")
    with pytest.raises(ExtractionFailed):
        _extractor(clean_db, BAD).extract(JD)


def test_schema_violation_raises_after_retry(clean_db):
    BAD = '{"skills": [{"raw_name": "RAG"}]}'   # 缺 importance/evidence_text
    calls = {"n": 0}
    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, json={"choices": [
            {"message": {"content": BAD}}]})
    http = httpx.Client(transport=httpx.MockTransport(handler))
    p = OpenAICompatibleProvider("https://t", "k", "m", http=http)
    with pytest.raises(ExtractionFailed, match="重试"):
        LLMSkillExtractor(LLMGateway(clean_db, p, "v1")).extract(JD)
    assert calls["n"] == 3          # 首次 + 重试 2（ADR-009 ≤2 次后明示）
```

- [ ] **Step 2: 验证失败** → **Step 3: 实现**

```python
"""LLM SkillExtractor（实现 Phase 2 冻结的 SkillExtractor 协议）。

失败语义（ADR-009 / API.md §2.1）：Schema 违反或证据不可溯 → 加错误提示重试 ≤2
→ 仍失败抛 ExtractionFailed（上层明示 LLM_EXTRACTION_FAILED，不降级不静默）。
"""
from __future__ import annotations

import json

from skillgap.extract.prompt import extraction_messages
from skillgap.ingest.extract import locate_evidence
from skillgap.llm.gateway import LLMGateway
from skillgap.models import JDExtraction, SkillAnnotation


class ExtractionFailed(RuntimeError):
    """抽取失败（Schema/证据校验，重试后）——明示，不降级。"""


def _parse_content(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return json.loads(text)


class LLMSkillExtractor:
    def __init__(self, gateway: LLMGateway, max_retries: int = 2):
        self.gateway = gateway
        self.max_retries = max_retries

    def extract(self, jd_text: str) -> list[SkillAnnotation]:
        last_error: Exception | None = None
        messages = extraction_messages(jd_text)
        for attempt in range(self.max_retries + 1):
            resp = self.gateway.chat(messages, response_json=True)
            try:
                data = _parse_content(resp.content)
                result = JDExtraction.model_validate(data)
                self._validate_evidence(jd_text, result)
                return result.skills
            except (json.JSONDecodeError, ValueError) as e:  # pydantic 校验失败
                last_error = e
                messages = messages[:2] + [
                    {"role": "assistant", "content": resp.content},
                    {"role": "user", "content":
                     f"输出未通过校验：{e}。请严格按规则重新输出 JSON"
                     "（evidence_text 必须是 JD 原文连续片段）。"},
                ]
        raise ExtractionFailed(f"抽取重试 {self.max_retries} 次后仍失败: {last_error}")

    @staticmethod
    def _validate_evidence(jd_text: str, result: JDExtraction) -> None:
        for s in result.skills:
            if not locate_evidence(jd_text, s.evidence_text):
                raise ValueError(
                    f"evidence_text 无法在 JD 原文定位: {s.evidence_text!r}")
        for r in result.soft_requirements:
            if not locate_evidence(jd_text, r.evidence_text):
                raise ValueError(
                    f"soft_requirement 证据无法定位: {r.evidence_text!r}")

    def extract_full(self, jd_text: str) -> JDExtraction:
        """供 analyzer 使用：返回含 soft_requirements 的完整抽取。"""
        # 复用 extract 的重试循环：直接调用 extract 拿 skills 后无法拿 soft——
        # 故 extract_full 为主流程，extract 为协议适配。
        ...
```

实现时把主循环放 `extract_full`（返回 JDExtraction），`extract` 调 `extract_full(...).skills` 以满足协议。

- [ ] **Step 4: 测试 PASS** → **Step 5: Commit** `feat(phase3): llm skill extractor with evidence validation and explicit failure`

### Task 6: JD Analyzer 服务（API §2.1 结构 + 回填）

**Files:** Create `src/skillgap/extract/analyzer.py`、Test `tests/test_analyzer.py`

- [ ] **Step 1: 失败测试**

```python
import httpx
from skillgap.extract.analyzer import analyze_jd
from skillgap.llm.provider import OpenAICompatibleProvider
from skillgap.llm.gateway import LLMGateway
from skillgap.extract.llm_extractor import LLMSkillExtractor
from tests.test_llm_extractor import GOOD

LLM_OK = httpx.Response(200, json={"choices": [
    {"message": {"content": GOOD}}], "usage": {"total_tokens": 88}})


def _analyzer(clean_db, handler):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    gw = LLMGateway(clean_db, OpenAICompatibleProvider("https://t", "k", "deepseek-chat", http=http), "v1")
    def _a(jd_text: str):
        return analyze_jd(clean_db, jd_text, extractor=LLMSkillExtractor(gw))
    return _a


JD = ("岗位职责：搭建 RAG 检索链路与 Agent 编排，优化 Prompt 工程。"
      "要求：1-3年大模型应用开发经验，精通 Python，熟悉 LangChain。") * 2


def test_analyze_jd_structure(clean_db):
    out = _analyzer(clean_db, lambda r: LLM_OK)(JD)
    assert out["job"]["language"] == "zh"
    assert out["job"]["market"] == "china"
    assert out["job"]["job_category"] == "ai_application_dev"
    assert out["core_skills"][0]["raw_name"] == "RAG"
    assert out["core_skills"][0]["evidence_text"]
    assert out["soft_requirements"][0]["type"] == "experience"
    assert out["extraction_meta"]["prompt_version"] == "v1"
    assert out["extraction_meta"]["model"] == "deepseek-chat"
    assert out["extraction_meta"]["latency_ms"] >= 0
    assert out["extraction_meta"]["total_tokens"] == 88


def test_short_jd_raises_validation(clean_db):
    import pytest
    with pytest.raises(ValueError, match="50"):
        _analyzer(clean_db, lambda r: LLM_OK)("太短")


def test_no_skill_jd_reports_empty_not_silent(clean_db):
    EMPTY = '{"skills": [], "soft_requirements": []}'
    resp = httpx.Response(200, json={"choices": [
        {"message": {"content": EMPTY}}]})
    out = _analyzer(clean_db, lambda r: resp)("岗位要求：负责部门日常事务管理与跨团队沟通协调工作。" * 5)
    assert out["core_skills"] == [] and out["secondary_skills"] == []
    assert out["extraction_meta"]["skill_count"] == 0   # 明示而非静默
```

- [ ] **Step 2: 验证失败** → **Step 3: 实现**

```python
"""POST /api/jd/analyze 的服务层（M1）。

无状态即时计算，默认不落库（API §2.1 B1 修复）；title 不猜（无输入），city/market
由确定性规则计算（normalize.py），LLM 只负责 skills + soft_requirements。
"""
from __future__ import annotations

import time

import psycopg

from skillgap.ingest.normalize import classify_job_category, detect_language
from skillgap.extract.llm_extractor import ExtractionFailed, LLMSkillExtractor
from skillgap.models import JDExtraction

MIN_LEN, MAX_LEN = 50, 20000   # 与 quality.py 口径一致


class JDValidationError(ValueError):
    pass


def analyze_jd(conn: psycopg.Connection, jd_text: str,
               extractor: LLMSkillExtractor,
               title: str = "") -> dict:
    text = jd_text.strip()
    if not (MIN_LEN <= len(text) <= MAX_LEN):
        raise JDValidationError(
            f"jd_text 长度 {len(text)} 不在 [{MIN_LEN}, {MAX_LEN}]")
    language = detect_language(text)
    started = time.monotonic()
    try:
        extraction: JDExtraction = extractor.extract_full(text)
    except ExtractionFailed as e:
        # API 错误码语义：LLM_EXTRACTION_FAILED —— 由 API 层转换，此处透传
        raise
    latency_ms = int((time.monotonic() - started) * 1000)
    core = [s for s in extraction.skills if s.importance == "must_have"]
    secondary = [s for s in extraction.skills if s.importance == "nice_to_have"]
    return {
        "job": {
            "title": title.strip(),
            "job_category": classify_job_category(title, text),
            "city": None,
            "market": "china" if language == "zh" else "global",
            "language": language,
        },
        "core_skills": [s.model_dump() for s in core],
        "secondary_skills": [s.model_dump() for s in secondary],
        "soft_requirements": [r.model_dump() for r in extraction.soft_requirements],
        "extraction_meta": {
            "model": extractor.gateway.provider.model,
            "prompt_version": extractor.gateway.prompt_version,
            "latency_ms": latency_ms,
            "total_tokens": 0,   # 由 extractor 返回时填充（见 extract_full 返回 meta）
            "skill_count": len(extraction.skills),
        },
    }
```

（实现时 `extract_full` 返回 `(JDExtraction, usage)` 或在 extractor 上暴露 `last_usage`，使 total_tokens 可填——以实际最小改动为准，测试断言 `total_tokens == 88`。）

- [ ] **Step 4: 测试 PASS** → **Step 5: Commit** `feat(phase3): jd analyzer service (stateless, api 2.1 shape)`

### Task 7: contribute 回填（Phase 2 遗留 extraction_status=pending）

**Files:** Modify `src/skillgap/extract/analyzer.py`（追加 backfill_pending）、Test `tests/test_analyzer.py` 追加

- [ ] **Step 1: 失败测试**

```python
def test_backfill_pending_jobs(clean_db):
    """Phase 2 遗留：user_submitted 无标注 → status=active + extraction_status=pending；
    回填后 job_skill 入库、pending 标记清除。"""
    from skillgap.ingest.contribute import contribute_jd
    from skillgap.extract.analyzer import backfill_pending
    r = contribute_jd(clean_db, JD, True, "AI 应用开发工程师")
    n = backfill_pending(clean_db, extractor=_ext(clean_db))
    assert n == 1
    with clean_db.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM job_skill WHERE job_id=%s", (r.job_id,))
        assert cur.fetchone()["c"] >= 1
        cur.execute("SELECT parsed_metadata->'extraction_status' AS s FROM job WHERE id=%s", (r.job_id,))
        assert cur.fetchone()["s"] is None
```

（`_ext` 为模块内 helper，构造 MockTransport GOOD 响应的 extractor。）

- [ ] **Step 2: 实现 backfill_pending**

```python
def backfill_pending(conn, extractor, limit: int = 100) -> int:
    """回填 extraction_status=pending 的 job（Phase 2 移交项）。失败明示：跳过并计数，不静默。"""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, raw_text FROM job
               WHERE parsed_metadata->>'extraction_status' = 'pending'
               ORDER BY id LIMIT %s""", (limit,))
        rows = cur.fetchall()
    done = 0
    for row in rows:
        try:
            anns = extractor.extract(row["raw_text"])
        except ExtractionFailed:
            continue    # 保持 pending，等 Prompt 迭代后重跑（明示：汇总返回数差值）
        with conn.cursor() as cur:
            from skillgap.ingest.extract import alias_map_from_db, resolve_skill_id, record_candidates
            amap = alias_map_from_db(conn)
            unresolved = []
            for a in anns:
                sid = resolve_skill_id(a.raw_name, amap)
                if sid is None:
                    unresolved.append(a.raw_name)
                    continue
                cur.execute(
                    """INSERT INTO job_skill (job_id, skill_id, importance, intensity,
                       evidence_text, extracted_by) VALUES (%s,%s,%s,%s,%s,'llm')
                       ON CONFLICT (job_id, skill_id) DO NOTHING""",
                    (row["id"], sid, a.importance, a.intensity, a.evidence_text))
            if unresolved:
                record_candidates(conn, unresolved, row["id"])
            cur.execute(
                """UPDATE job SET parsed_metadata = parsed_metadata - 'extraction_status'
                   WHERE id = %s""", (row["id"],))
        conn.commit()
        done += 1
    return done
```

- [ ] **Step 3: 测试 PASS** → **Step 4: Commit** `feat(phase3): backfill pending extractions from phase 2`

### Task 8: E1 种子标注集（20 条）

**Files:** Create `data/eval/e1_seed_v1.json`、`src/skillgap/eval/__init__.py`、`src/skillgap/eval/seed.py`、Test `tests/test_eval_seed.py`

- [ ] **Step 1: 标注集数据**（`data/eval/e1_seed_v1.json`，条目结构：

```json
[
  {
    "id": "seed-001",
    "jd_text": "岗位职责：负责大模型应用开发，搭建 RAG 检索链路与 Agent 编排，优化 Prompt 工程。任职要求：1-3年大模型应用开发经验，精通 Python，熟悉 LangChain 与 LangGraph，了解 Docker 部署。",
    "ground_truth": {
      "skills": [
        {"canonical_name": "RAG", "importance": "must_have"},
        {"canonical_name": "Python", "importance": "must_have"},
        {"canonical_name": "LangChain", "importance": "must_have"},
        {"canonical_name": "LangGraph", "importance": "must_have"},
        {"canonical_name": "Docker", "importance": "nice_to_have"},
        {"canonical_name": "Prompt Engineering", "importance": "must_have"}
      ]
    }
  }
]
```

要求：20 条（17 中文 + 3 英文），覆盖 ai_application_dev / ai_platform / backend / data / nlp 类别；ground truth 全部用词表 canonical_name（与 skills_v1.csv 对齐）；无 PII；jd_text 长度 50-20000。

- [ ] **Step 2: seed.py 入库（幂等）**

```python
"""E1 种子标注集入库（evaluation_sample，dataset_version=e1_seed_v1）。

真实收集 JD 到位后新增条目进 v2（EVALUATION_PLAN §6：不静默修改 v1）。
"""
from __future__ import annotations

import json
from pathlib import Path

import psycopg

SEED_PATH = Path(__file__).parents[2] / "data" / "eval" / "e1_seed_v1.json"
DATASET_VERSION = "e1_seed_v1"


def seed_eval(conn: psycopg.Connection) -> int:
    samples = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS c FROM evaluation_sample "
            "WHERE eval_type='skill_extraction' AND dataset_version=%s",
            (DATASET_VERSION,))
        if cur.fetchone()["c"] > 0:
            return 0        # 幂等：已入库
        for s in samples:
            cur.execute(
                """INSERT INTO evaluation_sample
                   (eval_type, input_payload, ground_truth, annotator, annotated_at, dataset_version)
                   VALUES ('skill_extraction', %s, %s, 'seed:manual', now(), %s)""",
                (json.dumps({"id": s["id"], "jd_text": s["jd_text"]},
                            ensure_ascii=False),
                 json.dumps(s["ground_truth"], ensure_ascii=False), DATASET_VERSION))
    conn.commit()
    return len(samples)
```

- [ ] **Step 3: 测试**

```python
from pathlib import Path
import json
from skillgap.eval.seed import SEED_PATH, DATASET_VERSION, seed_eval

TAXONOMY = Path("src/skillgap/taxonomy/data/skills_v1.csv")


def test_seed_file_shape():
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    assert 20 <= len(data) <= 30
    canon = {r.split(",")[0] for r in
             TAXONOMY.read_text(encoding="utf-8").splitlines()[1:]}
    for s in data:
        assert 50 <= len(s["jd_text"]) <= 20000
        names = [k["canonical_name"] for k in s["ground_truth"]["skills"]]
        assert all(n in canon for n in names), f"词表外 canonical_name: {names}"
        assert len(names) >= 3


def test_seed_eval_idempotent(clean_db):
    assert seed_eval(clean_db) == 20
    assert seed_eval(clean_db) == 0
    with clean_db.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM evaluation_sample "
                    "WHERE dataset_version=%s", (DATASET_VERSION,))
        assert cur.fetchone()["c"] == 20
```

- [ ] **Step 4: 测试 PASS** → **Step 5: Commit** `feat(phase3): e1 seed dataset v1 (20 samples)`

### Task 9: E1 评测器（P/R/F1 + 证据可溯 + 阈值 + eval_run 入库）

**Files:** Create `src/skillgap/eval/e1.py`、Test `tests/test_e1.py`

- [ ] **Step 1: 失败测试**

```python
import json
import pytest
from skillgap.eval.e1 import compute_metrics, verdict_for, run_e1
from skillgap.models import SkillAnnotation


def _anns(*pairs):
    return [SkillAnnotation(raw_name=n, importance=im, evidence_text="ev")
            for n, im in pairs]


def test_metrics_perfect():
    m = compute_metrics(
        extracted=[("RAG", "must_have")], truth=[("RAG", "must_have")])
    assert m["precision"] == 1.0 and m["recall"] == 1.0 and m["f1"] == 1.0
    assert m["importance_accuracy"] == 1.0


def test_metrics_partial_and_importance():
    m = compute_metrics(
        extracted=[("RAG", "must_have"), ("Docker", "must_have")],   # Docker 误报 + RAG 重要性错
        truth=[("RAG", "nice_to_have"), ("Python", "must_have")])    # Python 漏报
    assert m["precision"] == 0.5 and m["recall"] == 0.5 and m["f1"] == 0.5
    assert m["importance_accuracy"] == 0.0    # RAG 分错（0/1）


def test_metrics_macro_f1():
    m = compute_metrics(
        extracted=[("RAG", "must_have")],
        truth=[("RAG", "must_have"), ("Python", "must_have"),
               ("Docker", "must_have")])
    # RAG F1=1，Python/Docker F1=0 → macro = 1/3
    assert abs(m["macro_f1"] - round(1 / 3, 4)) < 1e-9


def test_verdict_thresholds():
    assert verdict_for({"f1": 0.9}) == "pass"
    assert verdict_for({"f1": 0.8}) == "warn"
    assert verdict_for({"f1": 0.6}) == "block"


def test_evidence_rate_is_hard_requirement():
    assert verdict_for({"f1": 0.9, "evidence_rate": 0.95}) == "block"


def test_run_e1_with_fake_extractor(clean_db):
    from skillgap.eval.seed import seed_eval
    from skillgap.taxonomy.seed import seed_all
    seed_all(clean_db); seed_eval(clean_db)

    class FakeExtractor:
        def __init__(self, conn):
            from skillgap.ingest.extract import alias_map_from_db
            self.amap = alias_map_from_db(conn)
            self.n = 0
        def extract(self, jd_text):
            self.n += 1
            # 返回词表内 3 个技能（语料无关，验证评测管道而非质量）
            return _anns(("Python", "must_have"), ("RAG", "must_have"),
                         ("Docker", "nice_to_have"))

    out = run_e1(clean_db, FakeExtractor(clean_db))
    assert out["sample_size"] == 20
    assert 0.0 <= out["f1"] <= 1.0
    assert out["evidence_rate"] == 1.0    # Fake 的 evidence_text 需能定位——见实现注
    with clean_db.cursor() as cur:
        cur.execute("SELECT metrics, verdict, eval_type, prompt_version FROM eval_run")
        row = cur.fetchone()
    assert row["eval_type"] == "skill_extraction" and row["verdict"] in (
        "pass", "warn", "block")
    assert row["prompt_version"] == "fake-v0"
```

（实现注：FakeExtractor 的 evidence_text "ev" 无法定位 → 评测器对不可定位证据按"该条抽取无效"计 evidence_rate，测试里 Fake 返回 `evidence_text` 取 jd_text 切片更真实——实现时给 Fake 用 `jd_text[:20]`。）

- [ ] **Step 2: 验证失败** → **Step 3: 实现**

```python
"""E1 技能抽取评测（EVALUATION_PLAN §2）。

红线：LLM 不参与指标计算；全部为集合运算与程序校验。
匹配判定：抽取经 alias 归一后与标注 canonical 集合比对。
"""
from __future__ import annotations

import json

import psycopg

from skillgap.ingest.extract import alias_map_from_db, resolve_skill_id

THRESHOLDS = {"pass": 0.85, "warn": 0.75}   # f1（micro）；<0.75 = block


def compute_metrics(extracted: list, truth: list) -> dict:
    """extracted/truth: (canonical_name, importance) 元组列表（已归一）。"""
    ext, tru = set(extracted), set(truth)
    tp = len(ext & tru)
    precision = tp / len(ext) if ext else 1.0
    recall = tp / len(tru) if tru else 1.0
    f1 = 2 * precision * recall / (precision + recall) if tp else 0.0
    # macro F1：逐技能二值匹配
    names = {n for n, _ in ext | tru}
    per = []
    for n in names:
        e_hit = (n, "must_have") in ext or (n, "nice_to_have") in ext
        t_hit = (n, "must_have") in tru or (n, "nice_to_have") in tru
        tp_i = int(e_hit and t_hit)
        p_i = tp_i / 1 if e_hit else 1.0
        r_i = tp_i / 1 if t_hit else 1.0
        per.append(2 * p_i * r_i / (p_i + r_i) if tp_i else 0.0)
    # 重要度准确率：tp 中 importance 一致的比例
    tp_detail = ext & tru
    imp_ok = sum(1 for n, i in tp_detail if (n, i) in set(extracted))
    return {
        "precision": round(precision, 4), "recall": round(recall, 4),
        "f1": round(f1, 4),
        "macro_f1": round(sum(per) / len(per), 4) if per else 0.0,
        "importance_accuracy": round(imp_ok / len(tp_detail), 4) if tp_detail else 0.0,
        "tp": tp, "extracted_count": len(ext), "truth_count": len(tru),
    }


def verdict_for(metrics: dict) -> str:
    if metrics.get("evidence_rate", 1.0) < 1.0:
        return "block"       # 证据可溯率 100% 硬要求
    f1 = metrics["f1"]
    if f1 >= THRESHOLDS["pass"]:
        return "pass"
    if f1 >= THRESHOLDS["warn"]:
        return "warn"
    return "block"


def run_e1(conn: psycopg.Connection, extractor,
           dataset_version: str = "e1_seed_v1",
           prompt_version: str = "fake-v0") -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT input_payload, ground_truth FROM evaluation_sample
               WHERE eval_type='skill_extraction' AND dataset_version=%s
               ORDER BY id""", (dataset_version,))
        samples = cur.fetchall()
    amap = alias_map_from_db(conn)
    agg_ext: list = []
    agg_truth: list = []
    evidence_total = evidence_ok = 0
    per_sample = []
    for s in samples:
        payload = s["input_payload"] if isinstance(s["input_payload"], dict) \
            else json.loads(s["input_payload"])
        truth = s["ground_truth"] if isinstance(s["ground_truth"], dict) \
            else json.loads(s["ground_truth"])
        try:
            anns = extractor.extract(payload["jd_text"])
            from skillgap.ingest.extract import locate_evidence
            ev_ok = all(locate_evidence(payload["jd_text"], a.evidence_text)
                        for a in anns)
        except Exception:
            anns, ev_ok = [], False     # 失败样本：抽取空集（拉低 recall），不中断
        evidence_total += 1
        evidence_ok += int(ev_ok)
        ext_pairs = []
        for a in anns:
            sid = resolve_skill_id(a.raw_name, amap)
            if sid is None:
                continue    # 词表外不进 P/R 统计（已进 new_skill_candidate 周级裁决）
            # canonical_name 查询
            with conn.cursor() as cur:
                cur.execute("SELECT canonical_name FROM skill WHERE id=%s", (sid,))
                cn = cur.fetchone()["canonical_name"]
            ext_pairs.append((cn, a.importance))
        tru_pairs = [(k["canonical_name"], k["importance"])
                     for k in truth["skills"]]
        m = compute_metrics(ext_pairs, tru_pairs)
        agg_ext.extend(ext_pairs)
        agg_truth.extend(tru_pairs)
        per_sample.append({"id": payload["id"], **m, "evidence_ok": ev_ok})

    overall = compute_metrics(agg_ext, agg_truth)
    overall["evidence_rate"] = round(evidence_ok / evidence_total, 4) \
        if evidence_total else 1.0
    overall["sample_size"] = len(samples)
    overall["prompt_version"] = prompt_version
    overall["dataset_version"] = dataset_version
    overall["verdict"] = verdict_for(overall)

    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO eval_run (eval_type, dataset_version, prompt_version,
               model, metrics, sample_size, verdict)
               VALUES ('skill_extraction', %s, %s, %s, %s, %s, %s)""",
            (dataset_version, prompt_version, getattr(extractor, "model_name", "unknown"),
             json.dumps(overall, ensure_ascii=False), len(samples), overall["verdict"]))
    conn.commit()
    return overall
```

- [ ] **Step 4: 测试 PASS** → **Step 5: Commit** `feat(phase3): e1 evaluator with pr/f1, evidence rate, thresholds, eval_run history`

### Task 10: CLI（jd-analyze / eval-e1 / backfill）+ 真实基线

**Files:** Modify `src/skillgap/cli.py`、Test `tests/test_cli.py` 追加

- [ ] **Step 1: cli.py 追加子命令（parser 注册 + 分支）**

```python
    p_jd = sub.add_parser("jd-analyze", help="粘贴 JD → 结构化分析（M1，不落库）")
    p_jd.add_argument("--file", required=True, help="JD 文本文件")
    p_jd.add_argument("--title", default="")

    p_ev = sub.add_parser("eval-e1", help="E1 抽取评测跑分（需 LLM_API_KEY）")
    p_ev.add_argument("--dataset-version", default="e1_seed_v1")
    p_ev.add_argument("--limit", type=int, default=0, help="0=全部")

    sub.add_parser("backfill-extraction",
                   help="回填 extraction_status=pending 的 job 抽取")
```

分支实现（复用注入模式，`db_url` 可测试）：

```python
        elif args.command == "jd-analyze":
            jd_text = Path(args.file).read_text(encoding="utf-8")
            extractor = _make_extractor(conn)
            try:
                _print(analyze_jd(conn, jd_text, extractor=extractor,
                                  title=args.title))
            except JDValidationError as e:
                print(f"错误：{e}", file=sys.stderr); return 1
            except ExtractionFailed as e:
                print(f"错误：LLM_EXTRACTION_FAILED：{e}", file=sys.stderr); return 1
        elif args.command == "eval-e1":
            seed_eval(conn)
            extractor = _make_extractor(conn)
            _print(run_e1(conn, extractor, dataset_version=args.dataset_version,
                          prompt_version=PROMPT_VERSION))
        elif args.command == "backfill-extraction":
            _print({"backfilled": backfill_pending(conn, _make_extractor(conn))})
```

`_make_extractor(conn)`：无 key 时打印"未配置 LLM_API_KEY（.env）"并 exit 2；有 key 构造 DeepSeek provider + gateway + LLMSkillExtractor。

- [ ] **Step 2: 测试（无 key 路径）**

```python
def test_jd_analyze_without_key_exits_clean(clean_db, capsys, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    from skillgap.config import Settings
    monkeypatch.setattr("skillgap.cli.settings",
                        Settings(llm_api_key=""), raising=False)
    rc = main(["jd-analyze", "--file", "x.txt"], db_url=TEST_URL)  # 文件可不存在先校验 key
    assert rc == 2
    assert "LLM_API_KEY" in capsys.readouterr().err
```

（以实现时最小改动为准：key 检查先于文件读取。）

- [ ] **Step 3: 全量回归** `pytest -q` → **Step 4: 真实基线（可选，用户提供 .env key）**

Run: `skillgap eval-e1` → 产出基线报告（F1/recall/evidence_rate/verdict），写入 eval_run。
预期：首轮 F1 大概率 0.7-0.9 区间；<0.75 时按 EVALUATION_PLAN §7 失败分诊（Prompt 措辞/词表覆盖）迭代，不放宽阈值。

- [ ] **Step 5: Commit** `feat(phase3): cli jd-analyze/eval-e1/backfill + baseline report`

### Task 11: 全量验证 + Phase 3 评审 + push

- [ ] `pytest -q` 全绿；`skillgap db-upgrade && skillgap seed && skillgap eval-e1` 冒烟
- [ ] 写 `PHASE_3_REVIEW.md`（六维自检 + E1 基线数字 + 遗留清单）+ ROADMAP 追加 Phase 3 记录
- [ ] `git push`（master → origin/main）；打 tag `phase-3`

---

## Self-Review 结论

1. **规格覆盖**：LLM Gateway（T2/T3）｜抽取 Schema（T4）｜LLM 抽取+证据校验+重试（T5）｜API §2.1 结构（T6）｜Prompt 版本管理（T4，PROMPT_VERSION 入 eval_run）｜E1 标注集（T8）｜P/R/F1+可溯率+阈值+回归历史（T9）｜CLI（T10）｜回填 Phase 2 遗留（T7）——全覆盖。
2. **占位符扫描**：T5 `extract_full` 的 `...` 与 T6 `total_tokens` 填充已注明实现注解决（以最小改动落地），其余无 TBD。
3. **类型一致性**：`LLMGateway(conn, provider, prompt_version)`、`LLMSkillExtractor(gateway)`、`analyze_jd(conn, jd_text, extractor, title)`、`run_e1(conn, extractor, dataset_version, prompt_version)` 各任务引用一致。
