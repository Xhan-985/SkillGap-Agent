"""词表 v1 正式建档（skill / skill_alias / skill_relation 种子；幂等可重跑）。"""
from __future__ import annotations

import csv
from importlib import resources

from skillgap.ingest.sources import seed_sources


def _read_csv(name: str) -> list[dict]:
    text = resources.files("skillgap.taxonomy").joinpath(f"data/{name}").read_text(
        encoding="utf-8-sig")
    return list(csv.DictReader(text.splitlines()))


def _split_aliases(value: str) -> list[str]:
    """alias 以 | 分隔；"-" 与空值表示无别名。"""
    if not value or value == "-":
        return []
    return [a.strip() for a in value.split("|") if a.strip() and a.strip() != "-"]


def seed_taxonomy(conn) -> dict:
    """返回 {"skills": n, "aliases": n, "relations": n}（含已存在的总数）。"""
    skills = _read_csv("skills_v1.csv")
    name_to_id: dict[str, int] = {}

    with conn.cursor() as cur:
        # 第一遍：无 parent 插入（幂等）
        for row in skills:
            cur.execute(
                """INSERT INTO skill (canonical_name, category, learning_cost,
                   esco_id, description)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (canonical_name) DO UPDATE SET
                     category = EXCLUDED.category,
                     learning_cost = EXCLUDED.learning_cost,
                     description = EXCLUDED.description
                   RETURNING id""",
                (row["canonical_name"], row["category"], row["learning_cost"],
                 None if row["esco_id"] == "-" else row["esco_id"],
                 row["description"] or None),
            )
            name_to_id[row["canonical_name"]] = cur.fetchone()["id"]
        # 第二遍：parent 关联（B2：Taxonomy 层级）
        for row in skills:
            if row["parent"] != "-":
                cur.execute(
                    "UPDATE skill SET parent_skill_id = %s WHERE id = %s",
                    (name_to_id[row["parent"]], name_to_id[row["canonical_name"]]))
        # 别名（全局唯一，幂等跳过）
        for row in skills:
            skill_id = name_to_id[row["canonical_name"]]
            for alias in _split_aliases(row["aliases_zh"]):
                cur.execute(
                    """INSERT INTO skill_alias (skill_id, alias, language)
                       VALUES (%s, %s, 'zh') ON CONFLICT (alias) DO NOTHING""",
                    (skill_id, alias))
            for alias in _split_aliases(row["aliases_en"]):
                cur.execute(
                    """INSERT INTO skill_alias (skill_id, alias, language)
                       VALUES (%s, %s, 'en') ON CONFLICT (alias) DO NOTHING""",
                    (skill_id, alias))
        # 关系（对称双行，评审 M3 关闭）
        for row in _read_csv("skill_relations_v1.csv"):
            cur.execute(
                """INSERT INTO skill_relation (skill_id, related_skill_id,
                   relation_type, note)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (skill_id, relation_type, related_skill_id)
                   DO UPDATE SET note = EXCLUDED.note""",
                (name_to_id[row["skill"]], name_to_id[row["related_skill"]],
                 row["relation_type"], row["note"]))
        cur.execute("SELECT count(*) AS c FROM skill")
        n_skills = cur.fetchone()["c"]
        cur.execute("SELECT count(*) AS c FROM skill_alias")
        n_alias = cur.fetchone()["c"]
        cur.execute("SELECT count(*) AS c FROM skill_relation")
        n_rel = cur.fetchone()["c"]
    conn.commit()
    return {"skills": n_skills, "aliases": n_alias, "relations": n_rel}


def seed_all(conn) -> None:
    """CLI/测试统一入口：来源注册表 + 词表。"""
    seed_sources(conn)
    seed_taxonomy(conn)
