"""skillgap CLI——数据层 + LLM 抽取入口（FastAPI 属后续 Phase）。

命令清单：
  db-upgrade / seed / import / ingest-adzuna / contribute /
  delete-contribution / quarantine-list / raw-cleanup / quality-report
  stats（支持切片）/ snapshot-create / skill-evidence / market-crosscheck（Phase 4）
  jd-analyze / eval-e1 / backfill-extraction（Phase 3，需 LLM_API_KEY）
  resume-analyze / profile-get / profile-add-skill / candidate-delete
    （Phase 5 Candidate Profile；resume-analyze 需 LLM_API_KEY）
  gap-get（Phase 6 Skill Gap：--job-id 单岗 或 --category 类目聚合，零 LLM）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skillgap import db
from skillgap.config import settings
from skillgap.eval.e1 import run_e1
from skillgap.eval.e2 import run_e2, seed_eval2
from skillgap.eval.seed import seed_eval
from skillgap.extract.analyzer import (
    JDValidationError, analyze_jd, backfill_pending,
)
from skillgap.extract.llm_extractor import (
    ExtractionFailed, LLMSkillExtractor,
)
from skillgap.extract.prompt import PROMPT_VERSION
from skillgap.gap.service import GapQueryError, JobNotFound, get_gaps
from skillgap.match.service import (
    CandidateNotFound as MatchCandidateNotFound,
    ExplanationInconsistency, JobNotFound as MatchJobNotFound, match_score,
)
from skillgap.recommend.service import (
    CandidateNotFound as RecCandidateNotFound, RecommendError, recommend,
)
from skillgap.ingest.adzuna import fetch_adzuna
from skillgap.ingest.collector import drop_last, run_collect
from skillgap.ingest.contribute import (
    ConsentRequired, QuarantinedContribution, contribute_jd, delete_contribution,
)
from skillgap.ingest.importer import parse_file
from skillgap.ingest.normalize import JOB_CATEGORIES
from skillgap.ingest.pipeline import run_batch
from skillgap.llm.embedding import EmbeddingError
from skillgap.llm.gateway import LLMGateway
from skillgap.llm.provider import LLMError, OpenAICompatibleProvider
from skillgap.profile.extractor import LLMResumeExtractor
from skillgap.profile.prompt import RESUME_PROMPT_VERSION
from skillgap.profile.service import (
    CandidateNotFound, ManualSkillError, ResumeValidationError,
    add_manual_skill, analyze_resume, delete_candidate, get_profile,
)
from skillgap.quality_metrics import quality_report
from skillgap.stats import (
    create_snapshot, crosscheck_baseline, skill_evidence, skill_frequency,
)
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

    p_ra = sub.add_parser("resume-analyze", help="简历文本 → 证据化画像（M5，需 key）")
    p_ra.add_argument("--file", required=True, help="简历纯文本文件")
    p_ra.add_argument("--candidate-id", type=int, default=None,
                      help="已有 candidate id（重分析=替换式，manual 行保留）")

    p_pg = sub.add_parser("profile-get", help="画像查询（API §2.6）")
    p_pg.add_argument("--candidate-id", type=int, required=True)

    p_pa = sub.add_parser("profile-add-skill",
                          help="手动勾选技能（manual 证据，confidence=1.0）")
    p_pa.add_argument("--candidate-id", type=int, required=True)
    p_pa.add_argument("--skill", required=True, help="词表内技能名")
    p_pa.add_argument("--level", type=int, required=True,
                      help="1-5 星（能力宣称强度）")
    p_pa.add_argument("--evidence", default=None, help="证据说明（缺省=手动勾选）")

    p_cd = sub.add_parser("candidate-delete", help="级联删除画像（API §2.7）")
    p_cd.add_argument("--candidate-id", type=int, required=True)

    p_gap = sub.add_parser("gap-get",
                           help="岗位要求 vs 画像差距量化（API §2.9，零 LLM）")
    p_gap.add_argument("--candidate-id", type=int, required=True)
    p_gap.add_argument("--job-id", type=int, default=None,
                       help="单岗模式：指定 job id")
    p_gap.add_argument("--category", default=None,
                       help="类目聚合模式（与 --job-id 二选一）")
    p_gap.add_argument("--market", default="china",
                       help="类目模式市场过滤（默认 china）")
    p_gap.add_argument("--min-freq", type=float, default=0.20,
                       help="类目模式入清单频率阈值（默认 0.20）")

    p_ms = sub.add_parser("match-score",
                          help="(画像, 岗位) 可解释匹配（M6，零 LLM）")
    p_ms.add_argument("--candidate-id", type=int, required=True)
    p_ms.add_argument("--job-id", type=int, required=True)
    p_ms.add_argument("--llm-explain", action="store_true",
                      help="LLM 生成解读（数字仍程序比对；失败降级模板）")

    p_ev2 = sub.add_parser("eval-e2",
                           help="E2 匹配评测跑分（需 LLM_API_KEY 物化样本）")
    p_ev2.add_argument("--dataset", default="data/eval/e2_seed_v1.json")
    p_ev2.add_argument("--seed-only", action="store_true",
                       help="仅入库标注集，不跑分")

    p_rec = sub.add_parser("recommend",
                           help="ROI 优先级建议（M9，零模型调用）")
    p_rec.add_argument("--candidate-id", type=int, required=True)
    p_rec.add_argument("--budget", type=int, default=14,
                       choices=(7, 14, 30),
                       help="学习预算天数（默认 14）")
    p_rec.add_argument("--market", default="china")
    p_rec.add_argument("--templates", default=None,
                       help="项目模板库路径（默认 data/project_templates.json）")

    p_agent = sub.add_parser("agent-plan",
                             help="Career Planner Agent 个性化建议叙事"
                                  "（LangGraph，需 LLM_API_KEY）")
    p_agent.add_argument("--candidate-id", type=int, required=True)
    p_agent.add_argument("--budget", type=int, default=14, choices=(7, 14, 30))
    p_agent.add_argument("--market", default="china")

    p_ev3 = sub.add_parser("eval-e3",
                           help="E3 推荐评测跑分（指标零 LLM；"
                                "标注集自动入库）")
    p_ev3.add_argument("--dataset", default="data/eval/e3_seed_v1.json")
    p_ev3.add_argument("--seed-only", action="store_true",
                       help="仅入库标注集，不跑分")
    p_ev3.add_argument("--judge", action="store_true",
                       help="附 LLM-as-judge 评分（Warn 级参考，需 "
                            "LLM_API_KEY；不影响 verdict）")

    p_ri = sub.add_parser("rag-index",
                          help="RAG 引用层：回填证据行 embedding（幂等，"
                               "需 EMBEDDING_API_KEY）")
    p_ri.add_argument("--batch-size", type=int, default=64)
    p_rs = sub.add_parser("rag-search",
                          help="RAG 语义检索：查询 → 证据行溯源"
                               "（需 EMBEDDING_API_KEY；可先 rag-index）")
    p_rs.add_argument("--query", required=True)
    p_rs.add_argument("--market", default=None,
                      choices=["china", "global"])
    p_rs.add_argument("--top-k", type=int, default=5)

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


def _make_resume_extractor(conn):
    """简历抽取器装配（prompt_version 独立——缓存表元数据可区分）。"""
    if not settings.llm_api_key:
        print("错误：未配置 LLM_API_KEY（.env 或环境变量），无法调用 LLM",
              file=sys.stderr)
        return None
    provider = OpenAICompatibleProvider(
        base_url=settings.llm_base_url, api_key=settings.llm_api_key,
        model=settings.llm_model, timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries)
    gateway = LLMGateway(conn, provider, RESUME_PROMPT_VERSION)
    return LLMResumeExtractor(gateway)


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
            _print(skill_frequency(conn, args.market, **_slice_kwargs(args)))
        elif args.command == "snapshot-create":
            _print(create_snapshot(conn, args.market, **_slice_kwargs(args)))
        elif args.command == "skill-evidence":
            _print(skill_evidence(conn, args.market, args.skill,
                                  **_slice_kwargs(args)))
        elif args.command == "market-crosscheck":
            _print(crosscheck_baseline(conn, args.market,
                                       **_slice_kwargs(args)))
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
        elif args.command == "resume-analyze":
            extractor = _make_resume_extractor(conn)   # key 检查先于文件读取
            if extractor is None:
                return 2
            resume_text = Path(args.file).read_text(encoding="utf-8")
            try:
                _print(analyze_resume(conn, resume_text,
                                      extractor=extractor,
                                      candidate_id=args.candidate_id))
            except (ResumeValidationError, CandidateNotFound,
                    ExtractionFailed, LLMError) as e:
                print(f"错误：{e}", file=sys.stderr)
                return 1
        elif args.command == "profile-get":
            try:
                _print(get_profile(conn, args.candidate_id))
            except CandidateNotFound as e:
                print(f"错误：{e}", file=sys.stderr)
                return 1
        elif args.command == "profile-add-skill":
            try:
                _print(add_manual_skill(conn, args.candidate_id, args.skill,
                                        args.level,
                                        evidence_text=args.evidence))
            except (CandidateNotFound, ManualSkillError) as e:
                print(f"错误：{e}", file=sys.stderr)
                return 1
        elif args.command == "candidate-delete":
            ok = delete_candidate(conn, args.candidate_id)
            print("204 deleted" if ok else "404 not_found")
            return 0 if ok else 1
        elif args.command == "gap-get":
            try:
                _print(get_gaps(conn, args.candidate_id, job_id=args.job_id,
                                category=args.category, market=args.market,
                                min_freq=args.min_freq))
            except (CandidateNotFound, JobNotFound) as e:
                print(f"错误：{e}", file=sys.stderr)
                return 1
            except GapQueryError as e:
                print(f"错误：{e}", file=sys.stderr)
                return 2
        elif args.command == "match-score":
            gateway = None
            if args.llm_explain:
                extractor = _make_extractor(conn)
                if extractor is None:
                    return 2
                gateway = extractor.gateway
            try:
                _print(match_score(conn, args.candidate_id, args.job_id,
                                   explain_llm=args.llm_explain,
                                   gateway=gateway))
            except (MatchCandidateNotFound, MatchJobNotFound) as e:
                print(f"错误：{e}", file=sys.stderr)
                return 1
            except ExplanationInconsistency as e:
                print(f"错误：LLM 解读数字不一致，已拦截：{e}",
                      file=sys.stderr)
                return 1
        elif args.command == "eval-e2":
            n = seed_eval2(conn, args.dataset)
            if args.seed_only:
                _print({"seeded": n})
                return 0
            extractor = _make_extractor(conn)
            if extractor is None:
                return 2
            try:
                _print(run_e2(conn, extractor))
            except (ValueError, ExtractionFailed, LLMError) as e:
                print(f"错误：{e}", file=sys.stderr)
                return 1
        elif args.command == "recommend":
            try:
                _print(recommend(conn, args.candidate_id,
                                 time_budget_days=args.budget,
                                 market=args.market,
                                 templates_path=args.templates))
            except RecCandidateNotFound as e:
                print(f"错误：{e}", file=sys.stderr)
                return 1
            except RecommendError as e:
                print(f"错误：{e}", file=sys.stderr)
                return 1
        elif args.command == "agent-plan":
            extractor = _make_extractor(conn)
            if extractor is None:
                return 2
            from skillgap.recommend.agent import run_planner
            try:
                _print(run_planner(conn, args.candidate_id,
                                   time_budget_days=args.budget,
                                   market=args.market,
                                   gateway=extractor.gateway))
            except (RecCandidateNotFound, RecommendError) as e:
                print(f"错误：{e}", file=sys.stderr)
                return 1
        elif args.command == "eval-e3":
            from skillgap.eval.e3 import (
                read_dataset_version, run_e3, seed_eval3,
            )
            judge_provider = None
            if args.judge:
                if not settings.llm_api_key:
                    print("错误：--judge 需要配置 LLM_API_KEY",
                          file=sys.stderr)
                    return 2
                # reasoner：temperature=None（不支持该参数）+ 长超时
                judge_provider = OpenAICompatibleProvider(
                    base_url=settings.llm_base_url,
                    api_key=settings.llm_api_key,
                    model=settings.llm_judge_model,
                    timeout=max(settings.llm_timeout, 180.0),
                    max_retries=1, temperature=None)
            try:
                version = read_dataset_version(args.dataset)
                n = seed_eval3(conn, args.dataset)
                if args.seed_only:
                    _print({"seeded": n})
                    return 0
                _print(run_e3(conn, dataset_version=version,
                              judge_provider=judge_provider))
            except (ValueError, RecommendError, RecCandidateNotFound,
                    ExtractionFailed, LLMError) as e:
                print(f"错误：{e}", file=sys.stderr)
                return 1
        elif args.command == "rag-index":
            from skillgap.retrieval.service import index_evidence
            try:
                n = index_evidence(conn, batch_size=args.batch_size)
                _print({"indexed": n,
                        "model": settings.embedding_model,
                        "dim": settings.embedding_dim})
            except (ValueError, EmbeddingError) as e:
                print(f"错误：{e}", file=sys.stderr)
                return 1
        elif args.command == "rag-search":
            from skillgap.retrieval.service import semantic_search
            try:
                _print({"query": args.query,
                        "market": args.market,
                        "results": semantic_search(
                            conn, args.query, market=args.market,
                            top_k=args.top_k)})
            except (ValueError, EmbeddingError) as e:
                print(f"错误：{e}", file=sys.stderr)
                return 1
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
