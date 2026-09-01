"""skillgap CLI——数据层 + LLM 抽取入口（FastAPI 属后续 Phase）。

命令清单：
  db-upgrade / seed / import / ingest-adzuna / contribute /
  delete-contribution / quarantine-list / raw-cleanup / quality-report / stats
  jd-analyze / eval-e1 / backfill-extraction（Phase 3，需 LLM_API_KEY）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skillgap import db
from skillgap.config import settings
from skillgap.eval.e1 import run_e1
from skillgap.eval.seed import seed_eval
from skillgap.extract.analyzer import (
    JDValidationError, analyze_jd, backfill_pending,
)
from skillgap.extract.llm_extractor import (
    ExtractionFailed, LLMSkillExtractor,
)
from skillgap.extract.prompt import PROMPT_VERSION
from skillgap.ingest.adzuna import fetch_adzuna
from skillgap.ingest.collector import drop_last, run_collect
from skillgap.ingest.contribute import (
    ConsentRequired, QuarantinedContribution, contribute_jd, delete_contribution,
)
from skillgap.ingest.importer import parse_file
from skillgap.ingest.pipeline import run_batch
from skillgap.llm.gateway import LLMGateway
from skillgap.llm.provider import LLMError, OpenAICompatibleProvider
from skillgap.quality_metrics import quality_report
from skillgap.stats import skill_frequency
from skillgap.taxonomy.seed import seed_all


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="skillgap")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("db-upgrade", help="应用未执行的 SQL 迁移")
    sub.add_parser("seed", help="词表 v1 + 来源注册表建档（幂等）")

    p_ing = sub.add_parser("ingest-adzuna", help="拉取 Adzuna 海外岗位（Global）")
    p_ing.add_argument("--country", default="gb")
    p_ing.add_argument("--query", default="LLM OR RAG OR AI engineer")
    p_ing.add_argument("--max-results", type=int, default=500)

    p_imp = sub.add_parser("import", help="CSV/JSON 批量导入")
    p_imp.add_argument("--file", required=True)

    p_con = sub.add_parser("contribute", help="匿名贡献 JD（opt-in）")
    p_con.add_argument("--title", required=True, help="岗位标题")
    p_con.add_argument("--file", required=True, help="JD 文本文件")
    p_con.add_argument("--source-hint", default="other")
    p_con.add_argument("--consent", action="store_true",
                       help="明确同意匿名贡献（必须显式传入）")

    p_del = sub.add_parser("delete-contribution", help="凭 deletion_code 删除贡献")
    p_del.add_argument("--code", required=True)

    sub.add_parser("quarantine-list", help="查看隔离队列")
    sub.add_parser("raw-cleanup", help="清理 7 天前的 raw 暂存（DATA_GOVERNANCE §5）")

    sub.add_parser("quality-report", help="E5 数据质量报告（JSON）")

    p_st = sub.add_parser("stats", help="频率统计空跑（S11 口径）")
    p_st.add_argument("--market", choices=["china", "global"], default="china")

    p_jd = sub.add_parser("jd-analyze",
                          help="粘贴 JD → 结构化分析（M1，不落库）")
    p_jd.add_argument("--file", required=True, help="JD 文本文件")
    p_jd.add_argument("--title", default="")
    p_col = sub.add_parser("collect",
                           help="交互式收集器：粘贴 JD→字段自动识别→回车确认→写批次 CSV")
    p_col.add_argument("--out", default="data/batch_1.csv",
                       help="输出批次 CSV 路径")
    p_col.add_argument("--file", dest="jd_file", default=None,
                       help="从文本文件读取一条 JD（绕开终端粘贴问题），处理后退出")
    p_col.add_argument("--drop-last", action="store_true", dest="drop_last",
                       help="删除批次 CSV 的最后一条记录（录错重录用）")

    p_ev = sub.add_parser("eval-e1", help="E1 抽取评测跑分（需 LLM_API_KEY）")
    p_ev.add_argument("--dataset-version", default="e1_seed_v1")

    sub.add_parser("backfill-extraction",
                   help="回填 extraction_status=pending 的 job 抽取")

    return p


def _make_extractor(conn):
    """DeepSeek provider + gateway + extractor；未配置 key → None（rc=2）。"""
    if not settings.llm_api_key:
        print("错误：未配置 LLM_API_KEY（.env 或环境变量），无法调用 LLM",
              file=sys.stderr)
        return None
    provider = OpenAICompatibleProvider(
        base_url=settings.llm_base_url, api_key=settings.llm_api_key,
        model=settings.llm_model, timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries)
    gateway = LLMGateway(conn, provider, PROMPT_VERSION)
    return LLMSkillExtractor(gateway)


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def main(argv: list[str] | None = None, db_url: str | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "collect":        # 纯本地交互，无需数据库
        if getattr(args, "drop_last", False):
            return drop_last(args.out)
        return run_collect(args.out, jd_file=getattr(args, "jd_file", None))
    conn = db.connect(db_url)

    try:
        if args.command == "db-upgrade":
            _print(db.upgrade(conn))
        elif args.command == "seed":
            seed_all(conn)
            _print({"status": "seeded"})
        elif args.command == "ingest-adzuna":
            report = fetch_adzuna(conn, country=args.country, query=args.query,
                                  max_results=args.max_results)
            _print(report.model_dump())
        elif args.command == "import":
            records = parse_file(args.file)
            report = run_batch(conn, records)
            _print(report.model_dump())
        elif args.command == "contribute":
            jd_text = Path(args.file).read_text(encoding="utf-8")
            try:
                result = contribute_jd(conn, jd_text=jd_text,
                                       consent=args.consent,
                                       title=args.title,
                                       source_hint=args.source_hint)
            except ConsentRequired as e:
                print(f"错误：{e}（未同意贡献，未入库；需显式传 --consent）",
                      file=sys.stderr)
                return 1
            except QuarantinedContribution as e:
                print(f"错误：{e}", file=sys.stderr)
                return 1
            _print({
                "job_id": result.job_id,
                "deduplicated": result.deduplicated,
                "pii_redaction": result.pii_redaction,
                "deletion_code": result.deletion_code,
                "note": "deletion_code 仅本次展示，请自行保存",
            })
        elif args.command == "delete-contribution":
            ok = delete_contribution(conn, args.code)
            print("204 deleted" if ok else "404 not_found（code 不存在或已删除）")
            return 0 if ok else 1
        elif args.command == "quarantine-list":
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, status, error, created_at FROM raw_jobs "
                    "WHERE status IN ('quarantined', 'failed') "
                    "ORDER BY created_at DESC LIMIT 50")
                _print(cur.fetchall())
        elif args.command == "raw-cleanup":
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM raw_jobs WHERE created_at < now() - "
                    "interval '7 days' RETURNING id")
                _print({"deleted": cur.rowcount})
            conn.commit()
        elif args.command == "quality-report":
            _print(quality_report(conn))
        elif args.command == "stats":
            _print(skill_frequency(conn, args.market))
        elif args.command == "jd-analyze":
            extractor = _make_extractor(conn)   # key 检查先于文件读取
            if extractor is None:
                return 2
            jd_text = Path(args.file).read_text(encoding="utf-8")
            try:
                _print(analyze_jd(conn, jd_text, extractor=extractor,
                                  title=args.title))
            except (JDValidationError, ExtractionFailed, LLMError) as e:
                print(f"错误：{e}", file=sys.stderr)
                return 1
        elif args.command == "eval-e1":
            extractor = _make_extractor(conn)
            if extractor is None:
                return 2
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM skill LIMIT 1")
                if cur.fetchone() is None:
                    print("错误：词表未初始化，请先运行 skillgap seed",
                          file=sys.stderr)
                    return 2
            seed_eval(conn)
            _print(run_e1(conn, extractor,
                          dataset_version=args.dataset_version))
        elif args.command == "backfill-extraction":
            extractor = _make_extractor(conn)
            if extractor is None:
                return 2
            _print({"backfilled": backfill_pending(conn, extractor)})
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
