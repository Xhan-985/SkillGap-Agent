"""Phase 11 T5：Data & Quality 页（UI_SPEC §2.7；D6 SSR 骨架 + JS fetch）
+ jd.html 贡献区（D7 opt-in 默认未勾 + 一次性 deletion_code 提示）。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from skillgap.api.app import create_app
from skillgap.api.deps import get_conn


@pytest.fixture()
def client(clean_db):
    app = create_app()

    def _override():
        yield clean_db

    app.dependency_overrides[get_conn] = _override
    with TestClient(app) as c:
        yield c, clean_db


def test_quality_page_200_title(client):
    """页面可达 + 标题（导航七页最后一页）。"""
    c, _ = client
    r = c.get("/quality")
    assert r.status_code == 200
    assert "数据与质量" in r.text


def test_quality_source_table_ssr(client):
    """来源分布 SSR 直出：seed 来源行 + Tier 列 + 条款核查日期列。"""
    c, conn = client
    html = c.get("/quality").text
    assert "条款核查日期" in html and "信任层级" in html
    names = [r["source_name"] for r in conn.execute(
        "SELECT source_name FROM data_source").fetchall()]
    for name in names:                    # 注册表行全部呈现（含空值占位 —）
        assert name in html


def test_quality_terms_checked_at_rendered(client):
    """terms_checked_at 呈现：seed 来源的核查日期逐行可见（UI_SPEC §2.7）。"""
    c, conn = client
    html = c.get("/quality").text
    rows = conn.execute(
        """SELECT source_name, terms_checked_at FROM data_source
           WHERE terms_checked_at IS NOT NULL""").fetchall()
    assert rows, "seed 来源应含条款核查日期"
    for row in rows:
        assert str(row["terms_checked_at"])[:10] in html


def test_quality_metrics_containers(client):
    """五指标卡容器（duplicate/missing/invalid/extraction/pii）存在。"""
    c, _ = client
    html = c.get("/quality").text
    for cid in ("qm-duplicate", "qm-missing", "qm-invalid",
                "qm-extraction", "qm-pii"):
        assert f'id="{cid}"' in html


def test_quality_eval_table_container(client):
    """评测历史表容器 + 加载占位（D6：JS fetch 填充）。"""
    c, _ = client
    html = c.get("/quality").text
    assert 'id="quality-eval-table"' in html
    assert "评测历史加载中" in html


def test_quality_governance_note(client):
    """治理声明摘要 + DATA_GOVERNANCE 链接（PII 边界/保留策略可答）。"""
    c, _ = client
    html = c.get("/quality").text
    assert "DATA_GOVERNANCE" in html
    assert "PII" in html and "deletion_code" in html


def test_quality_skeleton_no_metric_numbers(client):
    """骨架不硬编码指标数字（D6：数字只能来自 fetch 的 API——C5 反向锚定）。"""
    c, _ = client
    html = c.get("/quality").text
    assert "质量指标加载中" in html          # 空态占位在场
    for cid in ("qm-duplicate-val", "qm-missing-val"):
        # 容器内为占位符 "…"，而非任何数字
        idx = html.index(f'id="{cid}"')
        snippet = html[idx:idx + 120]
        for ch in "0123456789":
            assert ch not in snippet.split("</p>")[0]


def test_nav_seven_links_on_quality(client):
    """质量页自身导航七链接齐全（base.html 全站共享）。"""
    c, _ = client
    html = c.get("/quality").text
    for href in ("/", "/resume", "/jd", "/match", "/recommend", "/market",
                 "/quality"):
        assert f'href="{href}"' in html


def test_jd_contribute_section_hidden_unchecked(client):
    """D7：贡献区初始隐藏（分析成功后 JS 显示）+ 复选框默认未勾（opt-in）。"""
    c, _ = client
    html = c.get("/jd").text
    assert 'id="jd-contribute" hidden' in html
    assert 'id="jd-consent"' in html
    assert 'id="jd-consent" checked' not in html   # 默认未勾
    assert "默认不贡献" in html                     # opt-in 文案明示


def test_jd_contribute_elements(client):
    """贡献区元素：来源标签下拉（四选项）+ 提交按钮 + code 一次性提示。"""
    c, _ = client
    html = c.get("/jd").text
    assert 'id="jd-contribute-btn"' in html
    assert 'id="jd-source-hint"' in html
    for option in ('value="boss"', 'value="nowcoder"',
                   'value="liepin"', 'value="other"'):
        assert option in html
    assert "一次性展示" in html
    assert 'id="jd-contribute-result" hidden' in html


def test_appjs_contribute_and_quality_logic(client):
    """app.js：轮询 + 一次性展示渲染 + 质量页 fetch 两个 API 路径。"""
    c, _ = client
    js = c.get("/static/app.js").text
    assert "pollTask" in js and "/api/tasks/" in js
    assert "jd-contribute-btn" in js            # D7 分析成功后出现贡献区
    assert "/api/jd/contribute" in js
    assert "initQuality" in js
    assert "/api/quality/report" in js and "/api/eval/results" in js
