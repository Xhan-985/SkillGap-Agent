"""skillgap CLI——Phase 2 数据层入口（FastAPI 属后续 Phase）。

命令清单：
  db-upgrade / seed / import / ingest-adzuna / contribute /
  delete-contribution / quarantine-list / raw-cleanup / quality-report / stats
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skillgap import db
from skillgap.ingest.adzuna import fetch_adzuna
from skillgap.ingest.contribute import (
    ConsentRequired, QuarantinedContribution, contribute_jd, delete_contribution,
)
from skillgap.ingest.importer import parse_file
from skillgap.ingest.pipeline import run_batch
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

    return p


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def main(argv: list[str] | None = None, db_url: str | None = None) -> int:
    args = build_parser().parse_args(argv)
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
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
