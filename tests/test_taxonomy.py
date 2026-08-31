from skillgap.ingest.sources import get_source
from skillgap.taxonomy.seed import seed_all, seed_taxonomy


def test_seed_idempotent(clean_db):
    a = seed_taxonomy(clean_db)
    b = seed_taxonomy(clean_db)
    assert a == b                      # 重跑不翻倍
    assert a["skills"] == 30
    assert a["relations"] == 12
    assert a["aliases"] > 60


def test_seed_all_registers_sources(clean_db):
    seed_all(clean_db)
    az = get_source(clean_db, "adzuna")
    assert az["covers_market"] == "global"
    assert az["trust_tier"] == "tier_a"
    assert "Jobs by Adzuna" in az["attribution_html"]


def test_parent_link_exists(clean_db):
    seed_taxonomy(clean_db)
    with clean_db.cursor() as cur:
        cur.execute(
            """SELECT p.canonical_name AS parent, c.canonical_name AS child
               FROM skill c JOIN skill p ON c.parent_skill_id = p.id""")
        pairs = {(r["parent"], r["child"]) for r in cur.fetchall()}
    assert ("LangChain", "LangGraph") in pairs


def test_transferable_relation_symmetric(clean_db):
    seed_taxonomy(clean_db)
    with clean_db.cursor() as cur:
        cur.execute(
            """SELECT s1.canonical_name AS a, s2.canonical_name AS b
               FROM skill_relation r
               JOIN skill s1 ON r.skill_id = s1.id
               JOIN skill s2 ON r.related_skill_id = s2.id
               WHERE r.relation_type = 'transferable_to'""")
        pairs = {(r["a"], r["b"]) for r in cur.fetchall()}
    assert ("Java", "Python") in pairs and ("Python", "Java") in pairs
