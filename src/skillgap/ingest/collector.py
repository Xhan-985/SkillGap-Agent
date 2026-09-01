"""交互式人工收集器（S1 前端辅助——生成 collect_template 兼容 CSV）。

定位：把"Excel 里手拼 CSV/JSON 转义"变成问答式录入；推断全部走确定性
规则（词表 alias 扫描/正则），无 LLM；技能建议需人工逐条确认
（Tier A 人工标注集定位——建议不代替标注，importance/取舍由人定）。
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from skillgap.ingest.importer import HEADER_ALIASES
from skillgap.ingest.normalize import (
    JOB_CATEGORIES, classify_job_category, normalize_job_category,
    parse_salary_range,
)
from skillgap.ingest.pii import detect_pii, redact
from skillgap.ingest.quality import validate_jd

TAXONOMY_CSV = (Path(__file__).resolve().parent.parent
                / "taxonomy" / "data" / "skills_v1.csv")

# 模板列顺序（与 data/collect_template.csv 一致）
FIELD_ORDER = [
    "title", "company", "city", "country", "region",
    "salary_min", "salary_max", "salary_currency", "job_category",
    "raw_text", "soft_requirements", "skills", "source_type",
    "source_name", "source_url", "collected_at", "submitted_at",
    "consent_status", "data_quality",
]
# 反查首个中文表头（岗位名称 优先于 标题）
FIELD_TO_ZH: dict[str, str] = {}
for _zh, _en in HEADER_ALIASES.items():
    FIELD_TO_ZH.setdefault(_en, _zh)

INTENSITY_WORDS = ("精通", "熟练", "熟悉", "了解")

DEFAULT_SOURCE_TYPE = "public_job_page"
DEFAULT_SOURCE_NAME = "company_career_page"

# ---------- 粘贴优先：字段自动识别 ----------

# 岗位信号词（中英；命中即认为该片段是岗位名称）
_TITLE_SIGNALS = (
    "工程师", "架构师", "分析师", "经理", "专员", "总监", "主管", "开发",
    "研发", "算法", "顾问", "实习生",
    "engineer", "developer", "manager", "analyst", "scientist", "architect",
)
# JD 套话行——绝不当作标题
_BOILERPLATE_RE = re.compile(
    r"岗位职责|工作职责|任职要求|职位描述|工作内容|关于我们|工作地点|"
    r"薪资|薪酬|福利|responsibilit|requirement|qualification|job description|"
    r"about us|location|salary|benefit", re.IGNORECASE)
_TITLE_PREFIX_RE = re.compile(
    r"^(?:高薪招聘|岗位名称|职位名称|招聘岗位|诚聘|急聘|招聘|岗位|职位)"
    r"\s*[:：]?\s*")
_RECRUIT_WORD_RE = re.compile(r"(?:高薪招聘|诚聘|急聘|招聘)\s*[:：]?\s*")
_CUT_RE = re.compile(r"[，,。;；.·|/～~\-—\s]+$")

CITIES = (
    "北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "西安", "南京",
    "重庆", "长沙", "苏州", "天津", "合肥", "郑州", "青岛", "无锡", "厦门",
    "福州", "济南", "东莞", "佛山",
)


def extract_title(text: str) -> str | None:
    """从前几行非套话文本提取岗位名称（确定性规则，无 LLM）。"""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()][:5]
    for raw in lines:
        if _BOILERPLATE_RE.search(raw):
            continue
        candidate = _TITLE_PREFIX_RE.sub("", raw)
        m = _RECRUIT_WORD_RE.search(candidate)
        if m:
            candidate = candidate[m.end():]
        # 截到首个句读符（"某公司诚聘X工程师，负责…" → "X工程师"）
        candidate = re.split(r"[，,。;；]", candidate)[0].strip()
        candidate = _CUT_RE.sub("", candidate).strip("：: 　")
        if 2 <= len(candidate) <= 40 and _has_title_signal(candidate):
            return candidate
    return None


def _has_title_signal(candidate: str) -> bool:
    low = candidate.casefold()
    return any(s in low for s in _TITLE_SIGNALS)


def detect_company(text: str) -> str | None:
    # 排除"负责公司/在…公司/分公司"等动词/结构搭配，只认公司名
    for m in re.finditer(r"([\u4e00-\u9fa5A-Za-z0-9·（）()]{2,25}公司)", text):
        name = m.group(1)
        if not _COMPANY_STOP_RE.search(name):
            return name
    return None


_COMPANY_STOP_RE = re.compile(
    r"^(负责|在|于|加入|所在|任职|隶属|上市|分)公司?$"
    r"|分公司|子公司|总公司|集团公司$|负责公司")


def detect_city(text: str) -> str | None:
    for city in CITIES:
        if city in text:
            return city
    return None


# ---------- 纯函数层（可测） ----------

@dataclass(frozen=True)
class SkillSuggestion:
    canonical: str
    evidence_text: str
    intensity: str | None
    inferred: bool = False   # True = 措辞推断（非技术名直接命中）
    importance_hint: str = "must_have"   # 加分项章节/措辞推断的默认 importance


# importance 判定：加分章节标题 / 硬性章节标题 / 句内加分措辞
_NICE_SECTION_RE = re.compile(
    r"加分项|加分|优先条件| preferred |nice to have|plus", re.IGNORECASE)
_HARD_SECTION_RE = re.compile(
    r"任职要求|岗位要求|招聘要求|我们期望|职责|要求[:：]|requirement|"
    r"qualification|responsibilit", re.IGNORECASE)
_NICE_SENT_WORDS = ("加分", "优先", "者优先", "nice", "plus")


def _importance_hint(text: str, start: int, end: int,
                     intensity: str | None) -> str:
    """按证据位置推断 importance：加分章节/邻近加分措辞/了解级 → nice_to_have。"""
    if intensity == "了解":
        return "nice_to_have"
    # 邻近窗口：证据前 6 字符 + 证据后 12 字符（"者优先/加分"通常紧邻技能词；
    # 不用整句，避免同句其他技能的加分措辞误判本技能）
    near = text[max(0, start - 6):start] + text[end:end + 12]
    if any(w in near for w in _NICE_SENT_WORDS):
        return "nice_to_have"
    # 最近的上文章节标题（加分 vs 硬性，取更近者）
    nice_m = None
    for m in _NICE_SECTION_RE.finditer(text[:start]):
        nice_m = m
    if nice_m is None:
        return "must_have"
    hard_m = None
    for m in _HARD_SECTION_RE.finditer(text[:start]):
        hard_m = m
    if hard_m and hard_m.start() > nice_m.start():
        return "must_have"
    return "nice_to_have"


# 措辞推断：JD 写能力不写技术名时的补充建议（低误报措辞；已命中的不重复）
_HINT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(检索增强|知识库问答|文档问答|语义检索|向量检索)"),
     "RAG"),
    (re.compile(r"(提示词|(?<![A-Za-z])[Pp]rompt(?![A-Za-z]))"),
     "Prompt Engineering"),
    (re.compile(r"(容器化)"), "Docker"),
]


def load_alias_table(path: Path = TAXONOMY_CSV) -> list[tuple[str, str]]:
    """(alias, canonical) 匹配表：canonical 自身 + 中英别名；长 alias 优先。"""
    pairs: list[tuple[str, str]] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            canonical = (row.get("canonical_name") or "").strip()
            if not canonical:
                continue
            names = [canonical]
            for col in ("aliases_zh", "aliases_en"):
                for a in (row.get(col) or "").split("|"):
                    a = a.strip()
                    if a and a != "-":
                        names.append(a)
            pairs.extend((n, canonical) for n in names)
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return pairs


def _match_pattern(alias: str) -> re.Pattern:
    # 短 ASCII alias（如 py/mcp/java）加词边界：
    # 避免命中 happy 内部子串、JavaScript 里的 "java"
    if alias.isascii() and len(alias) <= 4:
        return re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])",
            re.IGNORECASE)
    return re.compile(re.escape(alias), re.IGNORECASE)


def _intensity_before(text: str, pos: int) -> str | None:
    window = text[max(0, pos - 8):pos]
    best, best_i = None, -1
    for w in INTENSITY_WORDS:
        i = window.rfind(w)
        if i > best_i:
            best, best_i = w, i
    return best


# 择一（alternation）检测：组内技能是"或"关系，无单独必需 → nice_to_have
_ALT_MARK_RE = re.compile(
    r"至少[^，,。；;\n]{0,12}一(?!\s*(?:年|个?月))"      # 至少一门/至少掌握一种
    r"|任选其一|(?:其中|以下)任一"
    r"|\bat least one\b(?!\s*(?:year|month))"            # 排除 at least one year
    r"|\bone of (?:them|which|the following)\b"
    r"|\bone or more\b|\beither\b")
_ALT_SEP_RE = re.compile(r"^\s*(?:/|\||或|or)\s*$", re.IGNORECASE)
_CLAUSE_BOUNDS = "。；;！？\n"


def _clause_of(text: str, start: int, end: int) -> str:
    """证据所在的子句（句读分号感叹问号换行为界；逗号不断句）。"""
    c0 = max(text.rfind(b, 0, start) for b in _CLAUSE_BOUNDS) + 1
    ends = [i for i in (text.find(b, end) for b in _CLAUSE_BOUNDS) if i != -1]
    return text[c0:min(ends) if ends else len(text)]


def _apply_alternation(text: str, found: dict[str, SkillSuggestion],
                       pos: dict[str, tuple[int, int]]) -> None:
    """规则A：子句含择一标记（至少一门/任选其一/one of）→ 组内技能降为加分。
    规则B：相邻两个证据之间只有 / 或 |（纯分隔符）→ 两者都降为加分。"""
    for canonical, (s, e) in pos.items():
        if _ALT_MARK_RE.search(_clause_of(text, s, e)):
            found[canonical] = replace(found[canonical],
                                       importance_hint="nice_to_have")
    ordered = sorted(pos.items(), key=lambda kv: kv[1][0])
    for (c1, span1), (c2, span2) in zip(ordered, ordered[1:]):
        if _ALT_SEP_RE.fullmatch(text[span1[1]:span2[0]]):
            for c in (c1, c2):
                found[c] = replace(found[c], importance_hint="nice_to_have")


def suggest_skills(text: str,
                   alias_table: list[tuple[str, str]]) -> list[SkillSuggestion]:
    """词表 alias 扫描 + 措辞推断：每个 canonical 只保留一个证据。"""
    found: dict[str, SkillSuggestion] = {}
    pos: dict[str, tuple[int, int]] = {}
    for alias, canonical in alias_table:
        if canonical in found:
            continue
        m = _match_pattern(alias).search(text)
        if m:
            intensity = _intensity_before(text, m.start())
            found[canonical] = SkillSuggestion(
                canonical=canonical,
                evidence_text=m.group(0),
                intensity=intensity,
                importance_hint=_importance_hint(text, m.start(), m.end(),
                                                 intensity))
            pos[canonical] = (m.start(), m.end())
    for pattern, canonical in _HINT_PATTERNS:
        if canonical in found:
            continue
        m = pattern.search(text)
        if m:
            intensity = _intensity_before(text, m.start())
            found[canonical] = SkillSuggestion(
                canonical=canonical, evidence_text=m.group(0),
                intensity=intensity, inferred=True,
                importance_hint=_importance_hint(text, m.start(), m.end(),
                                                 intensity))
            pos[canonical] = (m.start(), m.end())
    _apply_alternation(text, found, pos)
    return list(found.values())


def prepare_text(text: str) -> tuple[str, dict]:
    """PII 检测 + 自动替换（public_job_page 通道管道不脱敏——收集端先做）。"""
    findings = detect_pii(text)
    if not findings:
        return text, {}
    return redact(text, findings)


def build_row(*, title: str, raw_text: str,
              company: str | None = None, city: str | None = None,
              country: str | None = None, region: str | None = None,
              salary_min: int | None = None, salary_max: int | None = None,
              salary_currency: str | None = None,
              job_category: str | None = None,
              skills: list[dict] | None = None,
              source_type: str = DEFAULT_SOURCE_TYPE,
              source_name: str = DEFAULT_SOURCE_NAME,
              source_url: str | None = None,
              collected_at: str | None = None) -> dict:
    """组装模板行（英文键；中文表头由 append_row 负责映射）。"""
    return {
        "title": title, "company": company, "city": city,
        "country": country, "region": region,
        "salary_min": salary_min, "salary_max": salary_max,
        "salary_currency": salary_currency, "job_category": job_category,
        "raw_text": raw_text, "soft_requirements": "",
        "skills": skills or [], "source_type": source_type,
        "source_name": source_name, "source_url": source_url,
        "collected_at": collected_at or date.today().isoformat(),
        "submitted_at": "", "consent_status": "none",
        "data_quality": "human_reviewed",
    }


def append_row(path: str | Path, row: dict) -> Path:
    """追加一行到批次 CSV；新文件写中文表头 + BOM，追加不再写 BOM。

    skills/soft_requirements 为 list 时序列化为 JSON 字符串
    （importer 期望 CSV 单元格里是 JSON 文本）。
    """
    p = Path(path)
    exists = p.exists() and p.stat().st_size > 0
    mode, enc = ("a", "utf-8") if exists else ("w", "utf-8-sig")
    with open(p, mode, encoding=enc, newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow([FIELD_TO_ZH[k] for k in FIELD_ORDER])
        cells = []
        for k in FIELD_ORDER:
            v = row.get(k, "")
            if isinstance(v, (list, dict)):
                v = json.dumps(v, ensure_ascii=False)
            cells.append(v if v is not None else "")
        w.writerow(cells)
    return p


# ---------- 交互薄壳（不单测，smoke 覆盖） ----------

def _ask(prompt: str, default: str = "") -> str:
    suffix = f"（回车={default}）" if default else ""
    v = input(f"{prompt}{suffix}: ").strip()
    return v or default


def _read_jd() -> str:
    print("粘贴 JD 全文（多行直接回车换行），单独一行输入 END 结束：")
    lines: list[str] = []
    while True:
        line = input("> ")
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _confirm_skills(suggs: list[SkillSuggestion]) -> list[dict]:
    if not suggs:
        print("（词表未命中任何技能——本条可不标注，入库后由 LLM 补抽）")
        return []
    skills: list[dict] = []
    print("技能建议（[m]必须 [n]加分 [s]跳过；回车=建议默认；“推断”=由措辞推断，非技术名命中）：")
    for s in suggs:
        intensity = f"，强度识别：{s.intensity}" if s.intensity else ""
        tag = "，推断" if s.inferred else ""
        hint = "n" if s.importance_hint == "nice_to_have" else "m"
        hint_disp = "加分" if hint == "n" else "必须"
        ans = _ask(f"  {s.canonical}（证据“{s.evidence_text}”{intensity}{tag}，"
                   f"建议：{hint_disp}）", hint)
        if ans == "s":
            continue
        importance = "nice_to_have" if ans == "n" else "must_have"
        skills.append({"raw_name": s.canonical, "importance": importance,
                       "intensity": s.intensity, "evidence_text": s.evidence_text})
    return skills


def drop_last(out: str) -> int:
    """删除批次 CSV 的最后一条记录（录错了重录用；库中已导入的需另行处理）。"""
    p = Path(out)
    with p.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if len(rows) < 2:
        print("没有可删的数据行")
        return 1
    removed = rows.pop()
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)
    print(f"已删除最后一条: 岗位名称={removed[0] if removed else '?'}")
    print(f"剩余记录数: {len(rows) - 1}")
    return 0


def run_collect(out: str, jd_file: str | None = None) -> int:
    """交互主循环：粘贴 JD（或 --file 读取）→ 字段自动识别 → 确认 → 写入 CSV。

    --file：从文本文件读 JD（绕开终端多行粘贴丢字/乱码问题）。
    连续模式：每条处理完不退出——更新文件内容后回车读下一条，q 退出。
    """
    out_path = Path(out)
    alias_table = load_alias_table()
    count = 0
    mode = (f"读取 {jd_file}（每条保存后：更新文件→回车继续，q 退出）"
            if jd_file else "粘贴 JD 后自动识别")
    print(f"交互式收集器 → 写入 {out_path}（{mode}，回车即接受）")
    last_text: str | None = None
    first_round = True
    try:
        while True:
            print(f"\n=== 第 {count + 1} 条 ===")
            if jd_file:
                if not first_round:
                    ans = _ask(f"更新 {jd_file} 后回车继续（q 退出）", "")
                    if ans.strip().lower() == "q":
                        raise EOFError
                raw_text = Path(jd_file).read_text(
                    encoding="utf-8-sig").strip()
                if raw_text == last_text:
                    print("文件内容未变化，跳过（避免重复录入同一条 JD）")
                    continue
            else:
                raw_text = _read_jd()
            first_round = False
            if not raw_text:
                print("JD 全文为空，本条作废")
                continue
            if not jd_file:
                n_lines = len([l for l in raw_text.splitlines() if l.strip()])
                print(f"已接收 JD：{n_lines} 行 / {len(raw_text)} 字符"
                      "（若明显少于原文，说明粘贴被截断，请改用 --file 模式）")

            raw_text, pii_report = prepare_text(raw_text)
            if pii_report:
                print(f"PII 已自动替换：{pii_report['hits']}")

            title_guess = extract_title(raw_text)
            title = _ask("岗位名称" + (f"（识别：{title_guess}）" if title_guess else ""),
                         title_guess or "")
            if not title:
                print("岗位名称为空，本条作废")
                continue

            company_guess = detect_company(raw_text)
            company = _ask("公司" + (f"（识别：{company_guess}）" if company_guess else ""),
                           company_guess or "")

            city_guess = detect_city(raw_text)
            city = _ask("城市" + (f"（识别：{city_guess}）" if city_guess else ""),
                        city_guess or "")

            language = "zh" if any("\u4e00" <= ch <= "\u9fa5" for ch in raw_text) else "en"
            country_default = "中国" if language == "zh" and (city or company) else ""
            country = _ask("国家（可空）", country_default)
            region = _ask("区域（可空，如 华北）")

            verdict = validate_jd(title, raw_text)
            if verdict.verdict != "pass":
                print(f"质检提醒（{verdict.verdict}）：{verdict.reasons}"
                      "——可保存，导入时管道会复核")

            salary_min = salary_max = None
            salary_currency = ""
            lo, hi = parse_salary_range(raw_text)
            if lo:
                print(f"识别到薪资：{lo}-{hi}（月薪·元）")
                keep = _ask("采用该薪资？[y]/n", "y")
                if keep == "y":
                    salary_min, salary_max, salary_currency = lo, hi, "CNY"
                else:
                    salary_min = _ask("最低薪资（可空）") or None
                    salary_max = _ask("最高薪资（可空）") or None
                    if salary_min:
                        salary_currency = "CNY"

            category = classify_job_category(title, raw_text)
            job_category = _ask("岗位类别（识别：" + category + "）", category)
            if job_category not in JOB_CATEGORIES:
                fixed = normalize_job_category(job_category, title, raw_text)
                print(f"类别 '{job_category}' 不在枚举内，按规则归为：{fixed}")
                job_category = fixed

            skills = _confirm_skills(suggest_skills(raw_text, alias_table))

            source_url = _ask("来源链接 URL（public_job_page 必填；从浏览器地址栏复制）")

            row = build_row(
                title=title, raw_text=raw_text, company=company or None,
                city=city or None, country=country or None, region=region or None,
                salary_min=salary_min, salary_max=salary_max,
                salary_currency=salary_currency or None,
                job_category=job_category or None, skills=skills,
                source_url=source_url or None)
            append_row(out_path, row)
            count += 1
            last_text = raw_text
            print(f"已保存第 {count} 条 → {out_path}")

            if not jd_file:
                if _ask("继续下一条？[y]/n", "y") == "n":
                    break
    except EOFError:
        pass
    print(f"\n完成：共 {count} 条 → {out_path}")
    if count:
        print(f"导入命令：skillgap import --file {out_path}")
    return 0
