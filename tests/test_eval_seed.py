import json
from pathlib import Path

from skillgap.eval.seed import DATASET_VERSION, SEED_PATH, seed_eval

TAXONOMY = (Path(__file__).resolve().parents[1] / "src" / "skillgap"
            / "taxonomy" / "data" / "skills_v1.csv")


def _load_seed():
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


def _canonical_names():
    lines = TAXONOMY.read_text(encoding="utf-8").splitlines()[1:]
    return {r.split(",")[0] for r in lines if r.strip()}


def test_seed_file_size_and_shape():
    data = _load_seed()
    assert 20 <= len(data) <= 30
    for s in data:
        assert s["id"].startswith("seed-")
        assert 50 <= len(s["jd_text"]) <= 20000
        assert "skills" in s["ground_truth"]
        assert len(s["ground_truth"]["skills"]) >= 3


def test_ground_truth_uses_taxonomy_canonical_names():
    canon = _canonical_names()
    for s in _load_seed():
        names = [k["canonical_name"] for k in s["ground_truth"]["skills"]]
        outside = [n for n in names if n not in canon]
        assert not outside, f"词表外 canonical_name: {outside}（{s['id']}）"
        for k in s["ground_truth"]["skills"]:
            assert k["importance"] in ("must_have", "nice_to_have")


def test_seed_covers_mixed_languages():
    langs = {"zh": 0, "en": 0}
    for s in _load_seed():
        has_cjk = any("\u4e00" <= c <= "\u9fff" for c in s["jd_text"])
        langs["zh" if has_cjk else "en"] += 1
    assert langs["zh"] >= 15 and langs["en"] >= 3


def test_seed_eval_idempotent(clean_db):
    assert seed_eval(clean_db) == 20
    assert seed_eval(clean_db) == 0
    with clean_db.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM evaluation_sample "
                    "WHERE dataset_version=%s", (DATASET_VERSION,))
        assert cur.fetchone()["c"] == 20
