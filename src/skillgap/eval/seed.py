"""E1 种子标注集入库（evaluation_sample）。

v1（20 条合成变体）冻结；v2（53 条真实 JD：28 条人工确认行直取库内标注 +
25 条平台采集行逐条复核重标）新增，不静默修改 v1（EVALUATION_PLAN §6）。
标注口径：ground truth 用词表 canonical_name；JD 文本用真实变体表述
（别名/大小写），以同时检验抽取与 alias 归一。
"""
from __future__ import annotations

import json
from pathlib import Path

import psycopg

_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "eval"
SEED_VERSIONS: list[tuple[Path, str]] = [
    (_DATA_DIR / "e1_seed_v1.json", "e1_seed_v1"),
    (_DATA_DIR / "e1_seed_v2.json", "e1_seed_v2"),
]
DATASET_VERSION = "e1_seed_v1"   # 默认版本（回归基线）


def seed_eval(conn: psycopg.Connection) -> int:
    """幂等入库（逐版本独立判重）。返回本次插入总条数。"""
    inserted = 0
    for path, version in SEED_VERSIONS:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS c FROM evaluation_sample "
                "WHERE eval_type='skill_extraction' AND dataset_version=%s",
                (version,))
            if cur.fetchone()["c"] > 0:
                continue
            samples = json.loads(path.read_text(encoding="utf-8"))
            for s in samples:
                cur.execute(
                    """INSERT INTO evaluation_sample
                       (eval_type, input_payload, ground_truth, annotator,
                        annotated_at, dataset_version)
                       VALUES ('skill_extraction', %s, %s, 'seed:manual', now(), %s)""",
                    (json.dumps({"id": s["id"], "jd_text": s["jd_text"]},
                                ensure_ascii=False),
                     json.dumps(s["ground_truth"], ensure_ascii=False),
                     version))
            inserted += len(samples)
    conn.commit()
    return inserted
