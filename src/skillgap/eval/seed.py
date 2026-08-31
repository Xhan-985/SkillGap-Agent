"""E1 种子标注集入库（evaluation_sample，dataset_version=e1_seed_v1）。

真实收集 JD 到位后新增条目进 v2（EVALUATION_PLAN §6：不静默修改 v1）。
标注口径：ground truth 用词表 canonical_name；JD 文本用真实变体表述
（别名/大小写），以同时检验抽取与 alias 归一。
"""
from __future__ import annotations

import json
from pathlib import Path

import psycopg

SEED_PATH = Path(__file__).resolve().parents[3] / "data" / "eval" / "e1_seed_v1.json"
DATASET_VERSION = "e1_seed_v1"


def seed_eval(conn: psycopg.Connection) -> int:
    """幂等入库：已存在则跳过。返回本次插入条数。"""
    samples = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS c FROM evaluation_sample "
            "WHERE eval_type='skill_extraction' AND dataset_version=%s",
            (DATASET_VERSION,))
        if cur.fetchone()["c"] > 0:
            return 0
        for s in samples:
            cur.execute(
                """INSERT INTO evaluation_sample
                   (eval_type, input_payload, ground_truth, annotator,
                    annotated_at, dataset_version)
                   VALUES ('skill_extraction', %s, %s, 'seed:manual', now(), %s)""",
                (json.dumps({"id": s["id"], "jd_text": s["jd_text"]},
                            ensure_ascii=False),
                 json.dumps(s["ground_truth"], ensure_ascii=False),
                 DATASET_VERSION))
    conn.commit()
    return len(samples)
