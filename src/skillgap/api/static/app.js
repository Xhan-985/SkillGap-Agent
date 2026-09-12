/* SkillGap Agent 前端交互（Phase 10 T7，C6）
 * 约定：candidate_id 由本浏览器 localStorage 持有；所有 API 提交自动携带；
 * 失败一律红色横幅明示（UI_SPEC §2.2），不静默。
 * 零框架：原生 fetch + DOM（D2/C2）。 */
"use strict";

const CID_KEY = "skillgap_candidate_id";
const MATCH_KEY = "skillgap_last_match";

/* ---------- 公共 ---------- */

function getCid() { return localStorage.getItem(CID_KEY); }
function setCid(cid) { localStorage.setItem(CID_KEY, String(cid)); }
function clearCid() { localStorage.removeItem(CID_KEY); }

function $(id) { return document.getElementById(id); }

function showBanner(el, message) {
  el.textContent = message;
  el.hidden = false;
}
function hideBanner(el) { el.hidden = true; }

async function api(url, options) {
  const resp = await fetch(url, options);
  if (resp.status === 204) return null;
  let body = null;
  try { body = await resp.json(); } catch (_) { /* 非 JSON（罕见）*/ }
  if (!resp.ok) {
    const err = body && body.error;
    const detail = err && err.details
      ? "（" + JSON.stringify(err.details) + "）" : "";
    throw new Error((err && (err.code + ": " + err.message)) ||
                    ("HTTP " + resp.status)) + "";
  }
  return body;
}

function pct(x) { return Math.round(x * 100) + "%"; }

/* ---------- 简历分析 ---------- */

function initResume() {
  const form = $("resume-form");
  if (!form) return;
  const area = $("resume-text");
  area.addEventListener("input", () => {
    $("resume-counter").textContent = area.value.length + " 字符";
  });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    hideBanner($("resume-error"));
    try {
      const body = await api(form.dataset.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resume_text: area.value }),
      });
      setCid(body.candidate_id);
      $("resume-cid").textContent = body.candidate_id;
      renderResumeSkills(body.skills);
      $("resume-delete").dataset.endpoint =
        "/api/candidates/" + body.candidate_id;
      $("resume-result").hidden = false;
    } catch (err) {
      showBanner($("resume-error"), "简历分析失败：" + err.message);
    }
  });
  $("resume-delete").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!confirm(e.target.querySelector("button").dataset.confirm)) return;
    try {
      await api(e.target.dataset.endpoint, { method: "DELETE" });
      clearCid();
      $("resume-result").hidden = true;
      alert("画像已清空（级联删除匹配与推荐记录）。");
    } catch (err) {
      showBanner($("resume-error"), "删除失败：" + err.message);
    }
  });
}

function renderResumeSkills(skills) {
  $("resume-skills").innerHTML = skills.map((s) =>
    `<div class="skill-card conf-${confClass(s.confidence)}">
       <span class="skill-name">${esc(s.skill_id)}</span>
       <span class="stars">${"★".repeat(s.level)}${"☆".repeat(5 - s.level)}</span>
       <span class="conf">置信度 ${(+s.confidence).toFixed(2)}</span>
       <details><summary class="meta">证据链（${s.evidences.length}）</summary>
         <ul class="meta">${s.evidences.map((ev) =>
           `<li>[${esc(ev.type)} ×${ev.weight}] ${esc(ev.text)}</li>`).join("")}
         </ul></details>
     </div>`).join("");
}

function confClass(c) {
  return c >= 0.7 ? "high" : (c >= 0.4 ? "mid" : "low");
}

/* ---------- JD 分析 ---------- */

function initJd() {
  const form = $("jd-form");
  if (!form) return;
  const area = $("jd-text");
  area.addEventListener("input", () => {
    $("jd-counter").textContent = area.value.length + " 字符";
  });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    hideBanner($("jd-error"));
    try {
      const body = await api(form.dataset.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          jd_text: area.value, title: $("jd-title").value }),
      });
      renderJdResult(body);
      $("jd-result").hidden = false;
    } catch (err) {
      showBanner($("jd-error"), "JD 分析失败：" + err.message);
    }
  });
}

function renderJdResult(body) {
  const j = body.job;
  $("jd-job-card").innerHTML =
    `<div class="action-card"><strong>${esc(j.title || "未命名岗位")}</strong>
     <p class="meta">类别 ${esc(j.job_category)} · 市场 ${esc(j.market)} · ` +
    (j.city ? `城市 ${esc(j.city)} · ` : "") + `薪资 ${esc(j.salary || "—")}</p></div>`;
  const chip = (s) =>
    `<div class="action-card"><strong>${esc(s.raw_name)}</strong>
     <p class="meta">${esc(s.importance)} · ${esc(s.intensity)}</p>
     <blockquote class="meta">${esc(s.evidence_text)}</blockquote></div>`;
  $("jd-core").innerHTML = body.core_skills.map(chip).join("") || "（无）";
  $("jd-secondary").innerHTML = body.secondary_skills.map(chip).join("") || "（无）";
  $("jd-soft").innerHTML = body.soft_requirements.map((s) =>
    `<div class="action-card"><strong>${esc(s.type)}</strong>
     <p class="meta">${esc(s.value)} —— ${esc(s.evidence_text)}</p></div>`)
    .join("") || "（无）";
  $("jd-meta").textContent = JSON.stringify(body.extraction_meta, null, 2);
}

/* ---------- 匹配 ---------- */

function initMatch() {
  const form = $("match-form");
  if (!form) return;
  const cidInput = $("match-cid");
  if (getCid()) cidInput.value = getCid();
  $("match-use-text").addEventListener("change", (e) => {
    const useText = e.target.checked;
    $("match-jd").hidden = !useText;
    $("match-jobid-row").hidden = useText;
  });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    hideBanner($("match-error"));
    const payload = {
      candidate_id: parseInt(cidInput.value, 10),
      explain: $("match-explain").checked,
    };
    if ($("match-use-text").checked) payload.jd_text = $("match-jd").value;
    else payload.job_id = parseInt($("match-jobid").value, 10);
    try {
      const body = await api(form.dataset.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      localStorage.setItem(MATCH_KEY, JSON.stringify(body));
      renderMatch(body);
      $("match-result").hidden = false;
    } catch (err) {
      showBanner($("match-error"), "匹配失败：" + err.message);
    }
  });
}

function renderMatch(body) {
  setCid(body ? body.candidate_id || getCid() : getCid());
  $("match-version").textContent = "scoring_version " + body.scoring_version;
  const bd = body.breakdown;
  const bars = [
    ["coverage", "覆盖"], ["importance_coverage", "重要性覆盖"],
    ["evidence_quality", "证据质量"], ["experience_relevance", "经验相关"],
  ].map(([k, label]) =>
    `<div class="bar-row"><span class="bar-label">${label}</span>
     <div class="bar"><div class="bar-fill" style="width:${(bd[k] * 100).toFixed(1)}%"></div></div>
     <span class="bar-note">${(bd[k] * 100).toFixed(1)}%</span></div>`).join("");
  $("match-overview-main").innerHTML =
    `<div class="action-card"><strong style="font-size:22px">${(body.overall_score * 100).toFixed(1)}</strong>
     <ul class="bars">${bars}</ul></div>`;
  const lane = (arr, tpl) => arr.map(tpl).join("") || "（无）";
  $("match-strong").innerHTML = lane(body.strong_skills, (s) =>
    `<div class="skill-card conf-${confClass(s.confidence)}">
     <span class="skill-name">${esc(s.skill_id)}</span></div>`);
  $("match-weak").innerHTML = lane(body.weak_skills, (s) =>
    `<div class="skill-card"><span class="skill-name">${esc(s.skill_id)}</span>
     <span class="conf">${esc(s.note)}</span></div>`);
  $("match-missing").innerHTML = lane(body.missing_skills, (s) =>
    `<div class="skill-card"><span class="skill-name">${esc(s.skill_id)}</span>
     <span class="conf">${esc(s.required_importance)}</span></div>`);
  $("match-explanation").textContent = body.explanation;
}

/* ---------- 推荐 ---------- */

function initRecommend() {
  const form = $("recommend-form");
  if (!form) return;
  const cidInput = $("recommend-cid");
  if (getCid()) cidInput.value = getCid();
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    hideBanner($("recommend-error"));
    try {
      const body = await api(form.dataset.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          candidate_id: parseInt(cidInput.value, 10),
          time_budget_days: parseInt($("recommend-budget").value, 10),
          market: $("recommend-market").value,
        }),
      });
      $("recommend-version").textContent =
        "formula_version " + body.formula_version;
      $("recommend-table").querySelector("tbody").innerHTML =
        body.priority_items.map((it) =>
          `<tr><td>${esc(it.skill)}</td>
           <td>${pct(it.frequency)}（N=${it.sample_size}）</td>
           <td>${it.gap}</td><td>${esc(it.cost)}</td>
           <td>${(+it.potential_gain).toFixed(2)}</td></tr>`).join("");
      $("recommend-projects").innerHTML =
        body.project_suggestions.map((p) =>
          `<div class="action-card"><strong>${esc(p.title)}</strong>
           <p class="meta">覆盖技能：${p.skills.map(esc).join("、")} · 预估 ${p.est_days} 天 · 模板人工策划</p></div>`)
        .join("") || "（预算内无匹配模板）";
      $("recommend-result").hidden = false;
    } catch (err) {
      showBanner($("recommend-error"), "推荐生成失败：" + err.message);
    }
  });
}

/* ---------- Dashboard 匹配概览（C6：localStorage 呈现） ---------- */

function initDashboardMatchOverview() {
  const el = $("match-overview");
  if (!el) return;
  const raw = localStorage.getItem(MATCH_KEY);
  if (!raw) return;                       // SSR 空态文案已足够
  try {
    const body = JSON.parse(raw);
    const bd = body.breakdown;
    const bars = [
      ["coverage", "覆盖"], ["importance_coverage", "重要性覆盖"],
      ["evidence_quality", "证据质量"], ["experience_relevance", "经验相关"],
    ].map(([k, label]) =>
      `<div class="bar-row"><span class="bar-label">${label}</span>
       <div class="bar"><div class="bar-fill" style="width:${(bd[k] * 100).toFixed(1)}%"></div></div>
       <span class="bar-note">${(bd[k] * 100).toFixed(1)}%</span></div>`).join("");
    el.innerHTML =
      `<div class="action-card">
       <strong style="font-size:22px">${(body.overall_score * 100).toFixed(1)}</strong>
       <span class="meta">（最近一次匹配 · scoring_version ${esc(body.scoring_version)}）</span>
       <ul class="bars">${bars}</ul></div>`;
  } catch (_) { /* 损坏缓存视同无记录 */ }
}

/* ---------- 入口 ---------- */

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

document.addEventListener("DOMContentLoaded", () => {
  initResume();
  initJd();
  initMatch();
  initRecommend();
  initDashboardMatchOverview();
});
