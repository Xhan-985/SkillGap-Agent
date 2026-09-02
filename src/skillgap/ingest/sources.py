"""data_source 注册表种子（五来源，Trust Model 见 ADR-002）。"""
from __future__ import annotations

from datetime import date

DATA_SOURCES = [
    dict(
        source_type="public_api", source_name="adzuna", trust_tier="tier_a",
        license_or_usage_note=(
            "Adzuna ToS（核查 2026-08-31）：展示需带 'Jobs by Adzuna' 归属并链接 "
            "adzuna.co.uk；禁止以原始或聚合形式再分发；免费层 25 req/min、250 req/day"),
        attribution_html='<a href="https://www.adzuna.co.uk">Jobs by Adzuna</a>',
        covers_market="global", terms_checked_at=date(2026, 8, 31),
    ),
    dict(
        source_type="public_job_page", source_name="company_career_page",
        trust_tier="tier_a",
        license_or_usage_note=(
            "公司官方招聘页人工摘录（记录 source_url）；仅本项目内部统计用途，不分发原文"),
        attribution_html=None, covers_market="both",
        terms_checked_at=date(2026, 8, 31),
    ),
    dict(
        source_type="public_job_page", source_name="boss_zhipin",
        trust_tier="tier_b",
        license_or_usage_note=(
            "BOSS直聘公开职位页摘录（记录 source_url）；仅本项目内部统计用途，"
            "不分发原文；低频采集"),
        attribution_html=None, covers_market="china",
        terms_checked_at=date(2026, 9, 2),
    ),
    dict(
        source_type="user_submitted", source_name="user_contribution",
        trust_tier="tier_b",
        license_or_usage_note=(
            "用户 opt-in 匿名贡献（consent=market_analysis）；PII 脱敏后入库；"
            "deletion_code 支持删除（DATA_GOVERNANCE §3）"),
        attribution_html=None, covers_market="china",
        terms_checked_at=date(2026, 8, 31),
    ),
    dict(
        source_type="csv_import", source_name="community_csv", trust_tier="tier_c",
        license_or_usage_note="社区 CSV/JSON 批量贡献；过同一管道（PII/去重/质检）",
        attribution_html=None, covers_market="china",
        terms_checked_at=date(2026, 8, 31),
    ),
    dict(
        source_type="dataset_builtin", source_name="demo_dataset", trust_tier="tier_a",
        license_or_usage_note=(
            "项目自建 Demo Dataset（人工合规摘录，来源九字段完整；"
            "每批 50 条后校准词表，MVP §3）"),
        attribution_html=None, covers_market="china",
        terms_checked_at=date(2026, 8, 31),
    ),
]


def seed_sources(conn) -> None:
    with conn.cursor() as cur:
        for row in DATA_SOURCES:
            cur.execute(
                """INSERT INTO data_source (source_type, source_name, trust_tier,
                   license_or_usage_note, attribution_html, covers_market,
                   terms_checked_at)
                   VALUES (%(source_type)s, %(source_name)s, %(trust_tier)s,
                   %(license_or_usage_note)s, %(attribution_html)s,
                   %(covers_market)s, %(terms_checked_at)s)
                   ON CONFLICT (source_name) DO UPDATE SET
                   license_or_usage_note = EXCLUDED.license_or_usage_note,
                   attribution_html = EXCLUDED.attribution_html,
                   terms_checked_at = EXCLUDED.terms_checked_at""",
                row,
            )
    conn.commit()


def get_source(conn, source_name: str) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM data_source WHERE source_name = %s", (source_name,))
        row = cur.fetchone()
    if row is None:
        raise KeyError(f"未注册的数据来源: {source_name}（先运行 skillgap seed）")
    return row
