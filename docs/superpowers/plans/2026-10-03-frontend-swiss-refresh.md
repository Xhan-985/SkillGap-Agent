# Dashboard 瑞士网格风全站翻新 · 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Dashboard 七页从现状极简风格全站翻新为瑞士网格风（白底黑线 + 国际橙 + 超粗字重 + 2px 微圆角 + 零阴影零渐变），保持 DOM 语义与 540 测试零破坏。

**Architecture:** style.css 全量重写为令牌化设计系统（保留全部既有 class 名以兼容 JS/模板渲染），base.html 结构小改（分段市场切换/品牌），各页模板仅做标题结构化改造（page-head/panel-head），app.js 四处小改（星级点阵/大分数 class/导航激活态）。

**Tech Stack:** 纯手写 CSS（CSS 自定义属性）+ Jinja2 模板 + 原生 JS。零框架/零构建/零 CDN（C2 硬约束）。

**Spec:** `docs/superpowers/specs/2026-10-03-frontend-swiss-refresh-design.md`

**测试基线:** 540 passed（改动前先跑一次确认基线）。

---

### Task 0: 基线确认

- [ ] **Step 0.1** 跑全量测试确认基线：`& .venv\Scripts\python.exe -m pytest -q` → 预期 `540 passed`。若 Docker 未运行先 `docker compose up -d`（Postgres 依赖测试会静默 skip，警惕假绿）。
- [ ] **Step 0.2** 起服务供走查：`& .venv\Scripts\python.exe -m skillgap serve`（127.0.0.1:8000，保持后台运行；如 DB 未起先 `docker compose up -d`）。

### Task 1: style.css 全量重写（令牌 + 组件，核心交付）

**Files:**
- Modify: `src/skillgap/api/static/style.css`（整文件替换）

- [ ] **Step 1.1** 用以下内容**整文件替换** style.css：

```css
/* SkillGap Agent —— 瑞士网格风设计系统（2026-10-03 翻新）
 * 白底黑线 + 国际橙单强调 + 超粗字重 + 2px 微圆角 + 零阴影零渐变。
 * 反 AI 味清单：无紫渐变/无毛玻璃/无大圆角阴影卡/无 emoji/无位移动画。
 * 约束：零框架零构建零 CDN（C2）；无动画，仅 hover 换色（UI_SPEC §3）。 */

/* ---------- 令牌 ---------- */
:root {
  --ink: #111;            /* 正文/结构线/超粗标题 */
  --accent: #FF4F00;      /* 国际橙：激活态/关键数字/主 CTA */
  --muted: #555;          /* 次级文字 */
  --faint: #888;          /* 弱文字 */
  --line: #111;           /* 结构边框 1.5-2px */
  --hairline: #ddd;       /* 行内细分隔 1px */
  --paper: #fff;          /* 背景 */
  --radius: 2px;          /* 全局唯一圆角 */
  --font: system-ui, "Segoe UI", "Microsoft YaHei", sans-serif;
}

* { box-sizing: border-box; }
body {
  font-family: var(--font); margin: 0; color: var(--ink);
  background: var(--paper); font-variant-numeric: tabular-nums;
  font-size: 14px; line-height: 1.6;
}
a { color: var(--ink); text-decoration: underline; text-decoration-color: var(--accent); text-underline-offset: 3px; }
a:hover { color: var(--accent); }

/* ---------- 顶栏 ---------- */
.topbar {
  display: flex; gap: 28px; align-items: center;
  padding: 12px 24px; background: var(--paper);
  border-bottom: 2px solid var(--line); position: sticky; top: 0; z-index: 10;
}
.topbar .brand { font-weight: 800; font-size: 16px; letter-spacing: -0.01em; }
.topbar .brand i { color: var(--accent); font-style: normal; }
.topbar nav { display: flex; gap: 4px; }
.topbar nav a {
  color: var(--ink); text-decoration: none; font-size: 13px;
  letter-spacing: 0.05em; padding: 3px 10px; border-radius: var(--radius);
}
.topbar nav a:hover { border: 1.5px solid var(--line); padding: 1.5px 8.5px; color: var(--ink); }
.topbar nav a.on { background: var(--ink); color: var(--paper); font-weight: 600; }

/* 分段市场切换（base.html 配合） */
.segmented { margin-left: auto; display: flex; border: 1.5px solid var(--line); border-radius: var(--radius); overflow: hidden; }
.segmented a {
  color: var(--ink); text-decoration: none; font-size: 12px;
  letter-spacing: 0.08em; padding: 4px 12px; font-weight: 600;
}
.segmented a + a { border-left: 1.5px solid var(--line); }
.segmented a.on { background: var(--accent); color: var(--paper); }
/* 兼容旧 .market-switch（过渡期保险，base.html 已换 .segmented） */
.market-switch { margin-left: auto; font-size: 13px; }
.market-switch a { margin-left: 6px; color: var(--faint); text-decoration: none; }
.market-switch a.active { color: var(--ink); font-weight: 600; border-bottom: 2px solid var(--accent); }

/* ---------- 版心与页面头 ---------- */
main { max-width: 1200px; margin: 32px auto; padding: 0 24px; }
.page-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; border-bottom: 2px solid var(--line); padding-bottom: 12px; margin-bottom: 24px; }
.page-head h1 { font-size: 26px; font-weight: 800; letter-spacing: -0.01em; margin: 0; }
.page-head .hint { margin: 4px 0 0; }
.hint { color: var(--muted); font-size: 13px; }
.page-meta { font-size: 12px; color: var(--muted); letter-spacing: 0.05em; white-space: nowrap; }
h1 { font-size: 26px; font-weight: 800; }

/* ---------- 面板（编号面板） ---------- */
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.view { background: var(--paper); border: 1.5px solid var(--line); border-radius: var(--radius); padding: 0; }
.view > :last-child { margin-bottom: 16px; }
.view h2 { margin: 0; font-size: 15px; font-weight: 700; }
.panel-head { display: flex; align-items: baseline; gap: 10px; padding: 12px 16px 10px; border-bottom: 1px solid var(--hairline); margin-bottom: 12px; }
.panel-num { font-weight: 800; color: var(--accent); font-size: 14px; font-variant-numeric: tabular-nums; }
.panel-tag { margin-left: auto; font-size: 10px; letter-spacing: 0.12em; color: var(--faint); text-transform: uppercase; }
.view > h2:only-child { padding: 12px 16px 10px; border-bottom: 1px solid var(--hairline); margin-bottom: 12px; }
.view > *:not(.panel-head):not(h2) { margin-left: 16px; margin-right: 16px; }
.empty { color: var(--faint); }
.empty::before { content: "—— "; color: var(--accent); font-weight: 700; }

/* ---------- 技能行（点阵星级 + 置信度） ---------- */
.skill-card { display: flex; gap: 12px; align-items: baseline; padding: 6px 8px; border-top: 1px solid var(--hairline); margin-bottom: 0; }
.skill-card:first-child { border-top: none; }
.skill-name { min-width: 70px; font-weight: 600; }
.stars { letter-spacing: 2px; color: var(--ink); font-size: 12px; }
.stars::selection { color: var(--accent); }
.conf { font-size: 12px; color: var(--muted); margin-left: auto; }
/* 置信度三档：去背景色块；低置信橙左边线（语义保留 D5 精神） */
.skill-card.conf-low { border-left: 2px solid var(--accent); padding-left: 8px; }
.skill-card.conf-high, .skill-card.conf-mid { border-left: 2px solid transparent; padding-left: 8px; }

/* ---------- 市场条形 ---------- */
.bars { list-style: none; padding: 0; margin: 8px 0 0; }
.bar-row { display: grid; grid-template-columns: 90px 1fr 190px; gap: 10px; align-items: center; margin-bottom: 8px; }
.bar-label { font-size: 13px; font-weight: 600; }
.bar { background: var(--paper); border: 1px solid var(--line); height: 14px; border-radius: var(--radius); overflow: hidden; }
.bar-fill { background: var(--accent); height: 100%; }
.bar-note { font-size: 12px; color: var(--muted); }

/* ---------- 表格 ---------- */
table.roi { width: 100%; border-collapse: collapse; font-size: 13px; }
table.roi th, table.roi td { border-bottom: 1px solid var(--hairline); padding: 8px 10px; text-align: left; }
table.roi th { color: var(--muted); font-weight: 600; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; }
table.roi td { font-variant-numeric: tabular-nums; }

/* ---------- 行动卡与徽章 ---------- */
.action-card { border: 1.5px solid var(--line); border-radius: var(--radius); padding: 12px 14px; margin-bottom: 10px; background: var(--paper); }
.action-card p { margin: 6px 0 0; font-size: 13px; color: var(--muted); }
.priority { display: inline-block; background: var(--ink); color: var(--paper); font-size: 11px; font-weight: 700; letter-spacing: 0.05em; padding: 2px 8px; border-radius: var(--radius); margin-right: 8px; text-transform: uppercase; }
.score-big { font-size: 40px; font-weight: 800; color: var(--accent); font-variant-numeric: tabular-nums; letter-spacing: -0.02em; line-height: 1; }
.score-big small { font-size: 14px; color: var(--ink); font-weight: 600; }

/* ---------- 雷达（SVG 类名保留，配色瑞士化） ---------- */
.radar { width: 100%; max-width: 320px; display: block; margin: 0 auto; }
.radar-ring { fill: none; stroke: var(--hairline); }
.radar-required { fill: none; stroke: var(--ink); stroke-dasharray: 4 2; }
.radar-actual { fill: rgba(255, 79, 0, 0.18); stroke: var(--accent); }
.radar-label { font-size: 11px; fill: var(--muted); text-anchor: middle; }
.legend .swatch { display: inline-block; width: 12px; height: 12px; border-radius: var(--radius); vertical-align: -1px; }
.legend .swatch.actual { background: rgba(255, 79, 0, 0.55); border: 1px solid var(--accent); }
.legend .swatch.required { background: var(--paper); border: 1px dashed var(--ink); }

/* ---------- 灰态（D5 诚实语义） ---------- */
.gate-gray { background: var(--paper); border: 1.5px dashed var(--line); color: var(--muted); padding: 18px; border-radius: var(--radius); text-align: center; }
.gate-gray::before { content: "INSUFFICIENT · "; color: var(--accent); font-weight: 800; letter-spacing: 0.08em; }

/* ---------- 表单与按钮 ---------- */
button { background: var(--ink); color: var(--paper); border: 1.5px solid var(--ink); padding: 8px 18px; border-radius: var(--radius); cursor: pointer; font-size: 14px; font-weight: 600; }
button:hover { background: var(--paper); color: var(--ink); }
button.btn-accent { background: var(--accent); border-color: var(--accent); color: var(--paper); }
button.btn-accent:hover { background: var(--ink); border-color: var(--ink); }
button.danger { background: var(--paper); color: #b00; border: 1.5px solid var(--ink); }
button.danger:hover { background: #b00; color: var(--paper); border-color: #b00; }
textarea, input[type="text"], input[type="number"], select {
  border: 1.5px solid var(--line); border-radius: var(--radius); padding: 8px 10px;
  font-family: inherit; margin: 4px 0; background: var(--paper); font-size: 13px;
}
textarea:focus, input:focus, select:focus { outline: none; border: 2px solid var(--accent); padding: 7.5px 9.5px; }
form { margin: 12px 0; }
form label { margin-right: 16px; }
.banner-error { background: var(--paper); border: 1.5px solid #b00; color: #b00; padding: 10px 14px; border-radius: var(--radius); margin: 10px 0; font-weight: 600; }
code { background: var(--paper); border: 1px solid var(--hairline); padding: 1px 5px; border-radius: var(--radius); font-size: 0.92em; }

/* ---------- 泳道（流程页三栏） ---------- */
.swimlanes { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
.swimlanes h3 { font-size: 12px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: var(--muted); margin: 8px 0 6px; padding-bottom: 4px; border-bottom: 2px solid var(--line); }
h3 { font-size: 14px; font-weight: 700; }
blockquote { margin: 4px 0; padding: 6px 10px; background: var(--paper); border-left: 3px solid var(--accent); border-radius: var(--radius); color: var(--muted); }
details summary { cursor: pointer; color: var(--muted); font-size: 12px; }

/* ---------- 页脚 ---------- */
.meta { font-size: 12px; color: var(--muted); }
.foot { text-align: center; color: var(--faint); font-size: 11px; letter-spacing: 0.05em; padding: 20px; border-top: 1px solid var(--hairline); margin-top: 40px; }

/* ---------- 最小响应（桌面优先，仅一档） ---------- */
@media (max-width: 900px) {
  .grid, .swimlanes { grid-template-columns: 1fr; }
  .topbar { flex-wrap: wrap; gap: 12px; }
  .segmented { margin-left: 0; }
}
```

- [ ] **Step 1.2** 浏览器强刷 http://127.0.0.1:8000/ —— 确认无 404 样式、旧页面内容未被破坏（此时还是旧结构+新皮肤，出现混合态是预期）。
- [ ] **Step 1.3** 跑测试：`& .venv\Scripts\python.exe -m pytest tests/ -q` → `540 passed`（CSS 不触测试，保险）。
- [ ] **Step 1.4** Commit：`git add src/skillgap/api/static/style.css` + `git commit -m "feat(ui): style.css 全量重写为瑞士网格风令牌化设计系统（墨/国际橙/2px 微圆角/等宽数字；保留全部既有 class 兼容 JS 与模板渲染）"`

### Task 2: base.html 顶栏/页脚结构化

**Files:**
- Modify: `src/skillgap/api/templates/base.html`

- [ ] **Step 2.1** 品牌行 `<span class="brand">SkillGap Agent</span>` 改为 `<span class="brand">SkillGap<i>·</i>Agent</span>`。
- [ ] **Step 2.2** 市场切换整块 `<span class="market-switch">…</span>` 替换为分段控件：

```html
<nav class="segmented" aria-label="市场切换">
  <a class="{{ 'on' if market == 'china' else '' }}"
     href="/?market=china{% if candidate_id %}&amp;candidate_id={{ candidate_id }}{% endif %}">CHINA</a>
  <a class="{{ 'on' if market == 'global' else '' }}"
     href="/?market=global{% if candidate_id %}&amp;candidate_id={{ candidate_id }}{% endif %}">GLOBAL</a>
</nav>
```

- [ ] **Step 2.3** 跑模板相关测试：`& .venv\Scripts\python.exe -m pytest tests/test_api_app.py tests/test_api_market.py -q` → 全绿（TestClient 渲染 base.html）。若 `market` 变量在某上下文缺失导致 Jinja 报错，回退用 `market-switch` 旧类名 + CSS 已兼容样式，并在 commit message 记录。
- [ ] **Step 2.4** Commit：`git commit -m "feat(ui): base.html 顶栏瑞士化——品牌橙点 + 分段市场切换（CHINA/GLOBAL）"`

### Task 3: app.js 四处小改（星级点阵/大分数/导航激活态）

**Files:**
- Modify: `src/skillgap/api/static/app.js`

- [ ] **Step 3.1** `renderResumeSkills`（第 85 行）星级改点阵：

```js
`<span class="stars">${"●".repeat(s.level)}${"○".repeat(5 - s.level)}</span>`
```

- [ ] **Step 3.2** `renderMatch`（第 255 行）大分数改 class：`<strong style="font-size:22px">${body.overall_score.toFixed(1)}</strong>` → `<strong class="score-big">${body.overall_score.toFixed(1)}<small> /100</small></strong>`
- [ ] **Step 3.3** `initDashboardMatchOverview`（第 329 行）同样替换：`<strong style="font-size:22px">` → `<strong class="score-big">` 并补 `<small> /100</small>`。
- [ ] **Step 3.4** DOMContentLoaded 回调（第 399-405 行）末尾追加导航激活态：

```js
  document.querySelectorAll(".topbar nav a").forEach((a) => {
    if (a.getAttribute("href") === location.pathname) a.classList.add("on");
  });
```

- [ ] **Step 3.5** 浏览器验证：简历页粘贴简历提交 → 技能行显示 ●●●○○；匹配页跑一次 → 大分数橙色 40px。
- [ ] **Step 3.6** Commit：`git commit -m "feat(ui): app.js 星级改点阵●○ + 匹配大分数 score-big 类 + 顶栏导航激活态"`

### Task 4: dashboard.html —— 页面头 + 六编号面板 + SSR 星级

**Files:**
- Modify: `src/skillgap/api/templates/dashboard.html`

- [ ] **Step 4.1** 第 4-5 行页头替换：

```html
<header class="page-head">
  <div>
    <h1>总览</h1>
    <p class="hint">六视图数据全部来自服务端，可点击溯源；样本不足处如实灰显。</p>
  </div>
  <span class="page-meta">DASHBOARD · SSR</span>
</header>
```

- [ ] **Step 4.2** 六个 `<h2>` 全部换成 panel-head（编号/标签按下表，逐个替换）：

| 原行 | 替换为 |
|---|---|
| `<h2>我的画像</h2>` | `<div class="panel-head"><span class="panel-num">01</span><h2>我的画像</h2><span class="panel-tag">Profile</span></div>` |
| `<h2>技能雷达</h2>` | `<div class="panel-head"><span class="panel-num">02</span><h2>技能雷达</h2><span class="panel-tag">Radar</span></div>` |
| `<h2>市场热门技能</h2>` | `<div class="panel-head"><span class="panel-num">03</span><h2>市场热门技能</h2><span class="panel-tag">Market</span></div>` |
| `<h2>我的缺口</h2>` | `<div class="panel-head"><span class="panel-num">04</span><h2>我的缺口</h2><span class="panel-tag">Gap</span></div>` |
| `<h2>推荐行动</h2>` | `<div class="panel-head"><span class="panel-num">05</span><h2>推荐行动</h2><span class="panel-tag">Actions</span></div>` |
| `<h2>匹配概览</h2>` | `<div class="panel-head"><span class="panel-num">06</span><h2>匹配概览</h2><span class="panel-tag">Match</span></div>` |

- [ ] **Step 4.3** 第 16 行 SSR 星级改点阵：`{{ '★' * s.level }}{{ '☆' * (5 - s.level) }}` → `{{ '●' * s.level }}{{ '○' * (5 - s.level) }}`
- [ ] **Step 4.4** 浏览器走查总览页：六面板编号橙字、雷达橙描边、条形橙填充、灰态虚线框 N=0 前缀。
- [ ] **Step 4.5** `& .venv\Scripts\python.exe -m pytest tests/ -q` → `540 passed`。
- [ ] **Step 4.6** Commit：`git commit -m "feat(ui): 总览页瑞士化——page-head + 六视图编号面板(01-06) + SSR 星级点阵"`

### Task 5: market.html + quality.html

**Files:**
- Modify: `src/skillgap/api/templates/market.html`, `src/skillgap/api/templates/quality.html`

- [ ] **Step 5.1** market.html 第 4 行 `<h1>市场技能频率</h1>` 替换（其后若有 hint 行并入 div 内保留原文案）：

```html
<header class="page-head">
  <div>
    <h1>市场技能频率</h1>
    <p class="hint">（保留该页原有 hint 文案；若无为空删除此行）</p>
  </div>
  <span class="page-meta">MARKET</span>
</header>
```

- [ ] **Step 5.2** market.html 内若有 `.view` 区块则为其 `<h2>` 套 panel-head（无 h2 则跳过——该页 grep 仅见 h1）；Global 灰态视觉由 CSS `.gate-gray` 承担。
- [ ] **Step 5.3** quality.html 页头替换（同 5.1 模式，`<span class="page-meta">DATA &amp; QUALITY</span>`）。
- [ ] **Step 5.4** quality.html 三个 `<h2>` 套 panel-head：`来源分布（Tier 与条款核查）`→ num 01 tag Sources；`数据质量指标（E5）`→ 02 Quality；`评测历史`→ 03 Eval。
- [ ] **Step 5.5** 两页浏览器走查（quality 页表格大写表头/等宽数字；market 页条形+分段切换）。
- [ ] **Step 5.6** pytest 全量 → 540。Commit：`"feat(ui): 市场页/质量页瑞士化——page-head + 编号面板 + 表格大写表头"`

### Task 6: match.html + recommend.html

**Files:**
- Modify: `src/skillgap/api/templates/match.html`, `src/skillgap/api/templates/recommend.html`

- [ ] **Step 6.1** match.html `<h1>岗位匹配</h1>` → page-head（meta：`MATCH`）。
- [ ] **Step 6.2** match.html `<h2>匹配结果 <span class="meta" id="match-version"></span></h2>` → `<div class="panel-head"><span class="panel-num">01</span><h2>匹配结果</h2><span class="meta" id="match-version"></span><span class="panel-tag">Result</span></div>`
- [ ] **Step 6.3** recommend.html `<h1>学习推荐</h1>` → page-head（meta：`RECOMMEND`）。
- [ ] **Step 6.4** recommend.html `<h2>ROI 优先级 <span class="meta" id="recommend-version"></span></h2>` → `<div class="panel-head"><span class="panel-num">01</span><h2>ROI 优先级</h2><span class="meta" id="recommend-version"></span><span class="panel-tag">ROI</span></div>`；`<h3>项目建议</h3>` → `<div class="panel-head"><span class="panel-num">02</span><h3>项目建议</h3><span class="panel-tag">Projects</span></div>`
- [ ] **Step 6.5** 两页各表单的提交按钮加 `class="btn-accent"`（grep `type="submit"`，逐个加）。
- [ ] **Step 6.6** 走查：匹配页 Strong/Weak/Missing 三泳道大写泳道头；推荐页 P0 风格徽章（priority 类已瑞士化）+ 橙色提交按钮。
- [ ] **Step 6.7** pytest → 540。Commit：`"feat(ui): 匹配页/推荐页瑞士化——page-head + 编号面板 + 主 CTA 橙色按钮"`

### Task 7: resume.html + jd.html

**Files:**
- Modify: `src/skillgap/api/templates/resume.html`, `src/skillgap/api/templates/jd.html`

- [ ] **Step 7.1** resume.html `<h1>简历分析</h1>` → page-head（meta：`RESUME`）；`<h2>画像结果</h2>` → panel-head num 01 tag Profile；提交按钮加 `btn-accent`；删除表单保留 `danger` 类。
- [ ] **Step 7.2** jd.html `<h1>JD 分析</h1>` → page-head（meta：`JD`）；`<h2>分析结果</h2>` → panel-head num 01 tag Result；`<h3>匿名贡献到市场数据集</h3>` → `<div class="panel-head"><span class="panel-num">02</span><h3>匿名贡献到市场数据集</h3><span class="panel-tag">Contribute</span></div>`；贡献按钮加 `btn-accent`。
- [ ] **Step 7.3** 走查两页：泳道/卡片黑边面板、blockquote 橙左边、deletion_code code 样式。
- [ ] **Step 7.4** pytest → 540。Commit：`"feat(ui): 简历页/JD 页瑞士化——page-head + 编号面板 + 主 CTA"`

### Task 8: UI_SPEC §3 更新 + 零 CDN 核查

**Files:**
- Modify: `docs/UI_SPEC.md`

- [ ] **Step 8.1** 读 `docs/UI_SPEC.md`，定位 §3 设计原则段（含"桌面优先、无动画、够用即止"），替换设计语言描述为：

```markdown
- 设计语言：瑞士网格风（2026-10-03 翻新，spec: docs/superpowers/specs/2026-10-03-frontend-swiss-refresh-design.md）——白底黑线 + 国际橙（#FF4F00）单一强调色 + 超粗字重 + 2px 微圆角 + 零阴影零渐变；层级靠排印与网格；数字一律 tabular-nums；星级为 ●○ 点阵；低置信度 = 橙色左边线（不再用背景色块）。
- 交互约束不变：桌面优先、无动画（仅 hover 换色/边线加粗，无位移无过渡）；零框架零构建零 CDN（C2）。
```

（保留 §3 其余条款原文不动。）
- [ ] **Step 8.2** 零 CDN 核查：`grep -rn "https\?://" src/skillgap/api/templates src/skillgap/api/static` —— 仅允许 market.html 的 Adzuna 署名链接与 /api 溯源链接；不得出现外部 `<link>`/`<script src>`/`@import`。
- [ ] **Step 8.3** Commit：`"docs: UI_SPEC §3 设计语言更新为瑞士网格风 + 翻新说明"`

### Task 9: 全量验收

- [ ] **Step 9.1** pytest 全量 → `540 passed, 0 skipped`（Docker 在运行，警惕假绿）。
- [ ] **Step 9.2** 浏览器走查七页（/、/resume、/jd、/match、/recommend、/market、/quality）：截图存 `.superpowers/walkthrough/`（gitignored）。逐页检查：page-head 黑线、编号面板橙号、星级 ●○、条形橙填充、分段切换激活橙、灰态 N=0 虚线框、主 CTA 橙按钮、无外部资源加载（DevTools Network 无第三方请求）。
- [ ] **Step 9.3** 反 AI 味自查：无渐变（grep `gradient` = 0）、无 box-shadow 装饰（grep `box-shadow` = 0）、无 emoji、无紫色系色值。
- [ ] **Step 9.4** 汇总走查结果给用户终审；用户点头后按推送审批制询问是否 push。
