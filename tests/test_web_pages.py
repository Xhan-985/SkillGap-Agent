"""Phase 10 T6：Dashboard 页渲染——六视图 / fixture 数字 / 灰态 / 无硬编码（C5）。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from skillgap.api.app import create_app
from skillgap.api.deps import get_conn
from skillgap.recommend.service import recommend
from tests.test_recommend_service_fixtures import (
    seed_market, write_templates,
)


@pytest.fixture()
def client(clean_db):
    app = create_app()

    def _override():
        yield clean_db

    app.dependency_overrides[get_conn] = _override
    with TestClient(app) as c:
        yield c, clean_db


def _seed_full(conn, tmp_path):
    """seed_market（32 岗 agent_dev 市场 + 画像 A）+ 一条 recommendation
    ——三视图（雷达/市场/缺口+推荐）数据源一次到位。"""
    cid = seed_market(conn)
    recommend(conn, cid, templates_path=write_templates(tmp_path))
    return cid


def test_dashboard_six_views_and_fixture_numbers(client, tmp_path):
    """六区块存在 + fixture 数字出现（C5：数字必来自 fixture 而非硬编码）。"""
    c, conn = client
    cid = _seed_full(conn, tmp_path)
    r = c.get(f"/?candidate_id={cid}&market=china")
    assert r.status_code == 200
    html = r.text
    for block in ("view-profile", "view-radar", "view-market",
                  "view-gaps", "view-actions", "view-match"):
        assert f'id="{block}"' in html, block
    # 画像 fixture：技能名 + 星级（A：RAG L4 / Python L3）
    assert "RAG" in html and "Python" in html
    assert "★★★★☆" in html and "★★★☆☆" in html
    # 市场 fixture：N=32 + 频次 47%（Docker 15/32=0.4688 诊断实证）+ 置信度 low
    assert "N=32" in html and "47%" in html
    # 缺口表五列表头 + 推荐卡片
    for h in ("Skill", "Demand", "Gap", "Cost", "Potential Gain"):
        assert h in html
    assert "Priority 1" in html
    # 匹配概览：C6 容器 + 空态（T7 JS 填充）
    assert 'id="match-overview"' in html


def test_dashboard_insufficient_gray(client):
    """空库 global → N=0 灰态占位文案（D5：不隐藏、不无标注数字）。"""
    c, _ = client
    r = c.get("/?market=global")
    assert r.status_code == 200
    html = r.text
    assert "样本量不足以判断趋势（N=0）" in html
    assert 'class="gate-gray"' in html


def test_market_selector_persistent(client):
    """base.html 常驻市场选择器（UI_SPEC §1：China/Global 不可同时）。"""
    c, _ = client
    html = c.get("/?market=china").text
    assert 'href="/?market=china' in html
    assert 'href="/?market=global' in html
    # 当前市场高亮
    assert 'class="active"\n       href="/?market=china' in html.replace(
        'class="active"       href=', 'class="active"\n       href=')


def test_radar_svg_dual_polygons(client, tmp_path):
    """雷达 SVG：网格环 + required/actual 双多边形 + 顶点标签来自 fixture
    （category=agent_dev 对齐 seed_market 数据；顶点=缺口∪画像=4 个）。"""
    c, conn = client
    cid = _seed_full(conn, tmp_path)
    html = c.get(f"/?candidate_id={cid}&category=agent_dev").text
    assert "<svg" in html
    assert 'class="radar-required"' in html
    assert 'class="radar-actual"' in html
    assert html.count("radar-ring") >= 5          # 5 级网格环
    # 顶点：缺口技能（MCP/Docker 来自 seed_market 类目要求）+ 画像技能
    assert "MCP" in html and "Docker" in html
    assert "agent_dev" in html                     # 图例标注当前类目


def test_no_hardcoded_skill_names(client):
    """空库渲染：技能名零出现——无前端硬编码锚定（C5 红线）。"""
    c, _ = client
    html = c.get("/").text
    for name in ("RAG", "Python", "MCP", "Docker", "LangChain",
                 "FastAPI", "Java"):
        assert name not in html, name


def test_dashboard_candidate_missing_hint(client):
    """candidate_id 不存在 → 明示提示（诚实降级，不空白）。"""
    c, _ = client
    html = c.get("/?candidate_id=99999").text
    assert "不存在" in html


def test_static_style_served(client):
    """/static/style.css 可访问（D7 打包路径生效）。"""
    c, _ = client
    r = c.get("/static/style.css")
    assert r.status_code == 200
    assert "gate-gray" in r.text


# ---------- T7：流程页 ----------

PAGES = [
    ("/resume", "resume-form", "/api/resumes/analyze"),
    ("/jd", "jd-form", "/api/jd/analyze"),
    ("/match", "match-form", "/api/match"),
    ("/recommend", "recommend-form", "/api/recommendations"),
]


@pytest.mark.parametrize("path,form_id,endpoint", PAGES)
def test_flow_pages_render(client, path, form_id, endpoint):
    """四流程页渲染：表单指向契约端点 + 失败横幅容器 + JS 已引用。"""
    c, _ = client
    r = c.get(path)
    assert r.status_code == 200
    html = r.text
    assert f'id="{form_id}"' in html
    assert f'data-endpoint="{endpoint}"' in html
    assert "banner-error" in html          # 失败明示（UI_SPEC §2.2）
    assert "/static/app.js" in html        # base.html 常驻
    assert "localStorage" not in html or path != "/"   # JS 逻辑不内联


def test_market_page_ssr(client, tmp_path):
    """市场页 SSR 直出：频率表 + 窗口标注 + 证据链接（契约端点）。"""
    c, conn = client
    seed_market(conn)
    html = c.get("/market?market=china").text
    assert "N=32" in html
    assert "窗口" in html
    assert "/api/market/skills/" in html     # 证据溯源链接


def test_market_page_gray(client):
    """市场页空库 global → 灰态。"""
    c, _ = client
    html = c.get("/market?market=global").text
    assert "样本量不足以判断趋势（N=0）" in html


def test_appjs_served_and_cid_convention(client):
    """/static/app.js 可访问 + localStorage 键约定（C6）。"""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    js = r.text
    assert "skillgap_candidate_id" in js
    assert "skillgap_last_match" in js       # 匹配概览缓存键（C6）
    assert "fetch(" in js


def test_nav_links_all_pages(client):
    """base.html 导航六页链接齐全（流程串联导航）。"""
    c, _ = client
    html = c.get("/").text
    for href in ("/", "/resume", "/jd", "/match", "/recommend", "/market"):
        assert f'href="{href}"' in html


def test_resume_delete_confirm_copy(client):
    """画像删除二次确认文案（级联范围说明——UI_SPEC §2.3）。"""
    c, _ = client
    html = c.get("/resume").text
    assert "级联删除" in html
    assert "data-confirm" in html


def test_match_page_dual_mode_controls(client):
    """匹配页双模式控件：粘贴 JD 默认 + 岗位 ID 切换 + explain 可选。"""
    c, _ = client
    html = c.get("/match").text
    assert 'id="match-use-text"' in html and "checked" in html
    assert 'id="match-jobid"' in html
    assert 'id="match-explain"' in html
