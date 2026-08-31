"""交互式人工收集器（S1 前端辅助——生成 collect_template 兼容 CSV）。

定位：把"Excel 里手拼 CSV/JSON 转义"变成问答式录入；推断全部走确定性
规则（词表 alias 扫描/正则），无 LLM；技能建议需人工逐条确认
（Tier A 人工标注集定位——建议不代替标注，importance/取舍由人定）。
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from skillgap.ingest.importer import HEADER_ALIASES
from skillgap.ingest.normalize import (
    classify_job_category, parse_salary_range,
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


# ---------- 纯函数层（可测） ----------

@dataclass(frozen=True)
class SkillSuggestion:
    canonical: str
    evidence_text: str
    intensity: str | None


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
    # 短 ASCII alias（如 py/mcp）加词边界，避免命中 happy 之类内部子串
    if alias.isascii() and len(alias) <= 3:
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


def suggest_skills(text: str,
                   alias_table: list[tuple[str, str]]) -> list[SkillSuggestion]:
    """词表 alias 扫描：每个 canonical 只保留首个（最长 alias）命中。"""
    found: dict[str, SkillSuggestion] = {}
    for alias, canonical in alias_table:
        if canonical in found:
            continue
        m = _match_pattern(alias).search(text)
        if m:
            found[canonical] = SkillSuggestion(
                canonical=canonical,
                evidence_text=m.group(0),
                intensity=_intensity_before(text, m.start()))
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
    print("技能建议（词表命中；[m]必须 [n]加分 [s]跳过）：")
    for s in suggs:
        intensity = f"，强度识别：{s.intensity}" if s.intensity else ""
        ans = _ask(f"  {s.canonical}（证据“{s.evidence_text}”{intensity}）", "m")
        if ans == "s":
            continue
        importance = "nice_to_have" if ans == "n" else "must_have"
        skills.append({"raw_name": s.canonical, "importance": importance,
                       "intensity": s.intensity, "evidence_text": s.evidence_text})
    return skills


def run_collect(out: str) -> int:
    """交互主循环：逐条录入 → 推断 → 确认 → 追加写入 CSV。"""
    out_path = Path(out)
    alias_table = load_alias_table()
    count = 0
    print(f"交互式收集器 → 写入 {out_path}（表头自动生成，转义/JSON 全自动）")
    try:
        while True:
            print(f"\n=== 第 {count + 1} 条 ===")
            title = _ask("岗位名称（必填）")
            if not title:
                print("岗位名称为空，本条作废")
                continue
            company = _ask("公司（可空）")
            city = _ask("城市（可空）")
            country = _ask("国家（可空，默认中国）", "中国") if city else ""
            region = _ask("区域（可空，如 华北）")
            source_url = _ask("来源链接 URL（public_job_page 必填）")
            raw_text = _read_jd()
            if not raw_text:
                print("JD 全文为空，本条作废")
                continue

            raw_text, pii_report = prepare_text(raw_text)
            if pii_report:
                print(f"PII 已自动替换：{pii_report['hits']}")
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
            job_category = _ask("岗位类别（识别：" + category + "，可回车接受）",
                                category)

            skills = _confirm_skills(suggest_skills(raw_text, alias_table))

            row = build_row(
                title=title, raw_text=raw_text, company=company or None,
                city=city or None, country=country or None, region=region or None,
                salary_min=salary_min, salary_max=salary_max,
                salary_currency=salary_currency or None,
                job_category=job_category or None, skills=skills,
                source_url=source_url or None)
            append_row(out_path, row)
            count += 1
            print(f"已保存第 {count} 条 → {out_path}")

            if _ask("继续下一条？[y]/n", "y") == "n":
                break
    except EOFError:
        pass
    print(f"\n完成：共 {count} 条 → {out_path}")
    if count:
        print(f"导入命令：skillgap import --file {out_path}")
    return 0
