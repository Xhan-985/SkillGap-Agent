import json
from pathlib import Path

from skillgap.eval.seed import (
    DATASET_VERSION, SEED_VERSIONS, seed_eval,
)

TAXONOMY = (Path(__file__).resolve().parents[1] / "src" / "skillgap"
            / "taxonomy" / "data" / "skills_v1.csv")
V1_PATH = next(p for p, v in SEED_VERSIONS if v == "e1_seed_v1")
V2_PATH = next(p for p, v in SEED_VERSIONS if v == "e1_seed_v2")


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_names():
    lines = TAXONOMY.read_text(encoding="utf-8-sig").splitlines()[1:]
    return {r.split(",")[0] for r in lines if r.strip()}


def test_seed_file_size_and_shape():
    data = _load(V1_PATH)
    assert 20 <= len(data) <= 30
    for s in data:
        assert s["id"].startswith("seed-")
        assert 50 <= len(s["jd_text"]) <= 20000
        assert "skills" in s["ground_truth"]
        assert len(s["ground_truth"]["skills"]) >= 3


def test_ground_truth_uses_taxonomy_canonical_names():
    canon = _canonical_names()
    for path in (V1_PATH, V2_PATH):
        for s in _load(path):
            names = [k["canonical_name"] for k in s["ground_truth"]["skills"]]
            outside = [n for n in names if n not in canon]
            assert not outside, f"词表外 canonical_name: {outside}（{s['id']}）"
            for k in s["ground_truth"]["skills"]:
                assert k["importance"] in ("must_have", "nice_to_have")


def test_seed_covers_mixed_languages():
    langs = {"zh": 0, "en": 0}
    for s in _load(V1_PATH):
        has_cjk = any("\u4e00" <= c <= "\u9fff" for c in s["jd_text"])
        langs["zh" if has_cjk else "en"] += 1
    assert langs["zh"] >= 15 and langs["en"] >= 3


def test_v2_size_and_shape():
    """EVALUATION_PLAN §6：v2 为 50-100 条真实 JD，id 与 v1 不冲突。"""
    data = _load(V2_PATH)
    assert 50 <= len(data) <= 100
    v1_ids = {s["id"] for s in _load(V1_PATH)}
    for s in data:
        assert s["id"].startswith("v2-")
        assert s["id"] not in v1_ids
        assert 100 <= len(s["jd_text"]) <= 20000
        # 真实 JD 必含中文
        assert any("\u4e00" <= c <= "\u9fff" for c in s["jd_text"])


def test_v2_importance_balance():
    """复核重标后 must/nice 应大体均衡（全 must 说明复核缺位）。"""
    data = _load(V2_PATH)
    n_must = sum(1 for s in data for k in s["ground_truth"]["skills"]
                 if k["importance"] == "must_have")
    n_nice = sum(1 for s in data for k in s["ground_truth"]["skills"]
                 if k["importance"] == "nice_to_have")
    assert n_must > 0 and n_nice > 0
    # must 占比在 30%-70% 区间（真实 JD 的合理带宽）
    assert 0.3 < n_must / (n_must + n_nice) < 0.7


def test_seed_eval_idempotent(clean_db):
    assert seed_eval(clean_db) == 20 + len(_load(V2_PATH))
    assert seed_eval(clean_db) == 0
    with clean_db.cursor() as cur:
        for _, version in SEED_VERSIONS:
            cur.execute("SELECT count(*) AS c FROM evaluation_sample "
                        "WHERE dataset_version=%s", (version,))
            assert cur.fetchone()["c"] == len(_load(
                next(p for p, v in SEED_VERSIONS if v == version)))
        cur.execute("SELECT count(*) AS c FROM evaluation_sample "
                    "WHERE dataset_version=%s", (DATASET_VERSION,))
        assert cur.fetchone()["c"] == 20
