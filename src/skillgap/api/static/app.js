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
    throw new Error((err && (err.code + ": " + err.message)) ||
                    ("HTTP " + resp.status));
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
      $("jd-contribute").hidden = false;   // D7：分析成功后出现贡献区
    } catch (err) {
      showBanner($("jd-error"), "JD 分析失败：" + err.message);
    }
  });
  $("jd-contribute-btn").addEventListener("click", async () => {
    hideBanner($("jd-error"));
    $("jd-contribute-result").hidden = true;
    if (!$("jd-consent").checked) {
      showBanner($("jd-error"), "请先勾选同意贡献（opt-in，默认不贡献）。");
      return;
    }
    try {
      const task = await api("/api/jd/contribute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          jd_text: $("jd-text").value, consent: true,
          title: $("jd-title").value,
          source_hint: $("jd-source-hint").value }),
      });
      const done = await pollTask(task.task_id);
      renderContributeResult(done);
    } catch (err) {
      showBanner($("jd-error"), "贡献失败：" + err.message);
    }
  });
}

async function pollTask(taskId) {
  /* 轮询任务状态（1s 间隔，60s 上限——本地单任务管道足够）；终态
     completed/failed 返回；deletion_code 一次性展示在 renderContributeResult。 */
  for (let i = 0; i < 60; i++) {
    const t = await api("/api/tasks/" + taskId);
    if (t.status === "completed" || t.status === "failed") return t;
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("任务轮询超时（60s）——请稍后重试");
}

function renderContributeResult(t) {
  const el = $("jd-contribute-result");
  if (t.status === "failed") {
    el.className = "banner-error";
    el.innerHTML = `贡献未通过：${esc(t.error || "未知原因")}` +
      `<p class="meta">（质检隔离的原文进入人工复核队列，不会入库统计）</p>`;
    el.hidden = false;
    return;
  }
  el.className = "action-card";
  const pii = t.pii_redaction;
  const piiNote = pii && Object.keys(pii.hits || {}).length
    ? `已检测并替换 PII：${Object.entries(pii.hits)
        .map(([k, v]) => `${esc(k)} ×${v}`).join("、")}` : "未检测到 PII";
  if (t.deduplicated) {
    el.innerHTML = `<strong>内容已存在（deduplicated）</strong>
      <p class="meta">复用既有岗位 #${t.job_id}，未重复入库。</p>
      <p class="meta">${esc(piiNote)}</p>`;
  } else {
    const extract = t.extraction_status === "done" ? "已完成" : "待回填（pending）";
    el.innerHTML = `<strong>贡献成功（岗位 #${t.job_id}，技能抽取${esc(extract)}）</strong>
      <p class="meta">${esc(piiNote)}</p>
      <p class="meta">deletion_code（<strong style="color:#b00">一次性展示，请立即保存</strong>——离开本页后不可再查看）：</p>
      <p style="font-size:22px;letter-spacing:2px"><code>${esc(t.deletion_code || "—")}</code></p>
      <p class="meta">删除贡献：DELETE /api/contributions/${esc(t.deletion_code || "")}</p>`;
  }
  el.hidden = false;
}

function renderJdResult(body) {
  const j = body.job;
  $("jd-job-card").innerHTML =
    `<div class="action-card"><strong>${esc(j.title || "未命名岗位")}</strong>
     <p class="meta">类别 ${esc(j.job_category)} · 市场 ${esc(j.market)} · ` +
    (j.city ? `城市 ${esc(j.city)} · ` : "") + `薪资 ${esc(j.salary || "—")}</p></div>`;
  const chip = (s) =>
    `<div class="action-card"><strong>${esc(s.raw_name)}</strong>
     <p class="meta">${esc(s.importance)}${s.intensity ? " · " + esc(s.intensity) : ""}</p>
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
    `<div class="action-card"><strong style="font-size:22px">${body.overall_score.toFixed(1)}</strong>
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
           <p class="meta">覆盖技能：${p.matched_skills.map(esc).join("、")} · 预估 ${p.est_days} 天 · 模板人工策划</p></div>`)
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
       <strong style="font-size:22px">${body.overall_score.toFixed(1)}</strong>
       <span class="meta">（最近一次匹配 · scoring_version ${esc(body.scoring_version)}）</span>
       <ul class="bars">${bars}</ul></div>`;
  } catch (_) { /* 损坏缓存视同无记录 */ }
}

/* ---------- 数据与质量页（D6：SSR 骨架 + fetch 填充） ---------- */

function initQuality() {
  if (!$("quality-metrics")) return;
  api("/api/quality/report").then((q) => {
    $("quality-computed-at").textContent =
      "计算时间 " + q.computed_at + "（批次三率来自 ingest_batch 聚合，全库两率为实时扫描）";
    $("qm-duplicate-val").textContent = (+q.duplicate_rate).toFixed(4);
    $("qm-missing-val").textContent = (+q.missing_field_rate).toFixed(4);
    $("qm-invalid-val").textContent = (+q.invalid_jd_rate).toFixed(4);
    $("qm-extraction-val").textContent =
      (+q.skill_extraction_error_rate).toFixed(4);
    const pii = q.pii_detection;
    const audit = pii.manual_audit_pass == null
      ? "待人工抽查" : (pii.manual_audit_pass ? "通过" : "未通过");
    $("qm-pii-val").textContent =
      `命中率 ${(+pii.hit_rate).toFixed(4)} · 规则 ${esc(pii.rules_version)}` +
      ` · 扫描 ${pii.scan_count} 条 · 人工抽查 ${audit}`;
  }).catch((err) => {
    $("quality-computed-at").textContent = "质量指标加载失败：" + err.message;
  });
  api("/api/eval/results").then((r) => {
    const rows = r.runs;
    if (!rows.length) {
      $("quality-eval-note").textContent = "暂无评测记录（eval_run 空）。";
      return;
    }
    $("quality-eval-note").hidden = true;
    const mainMetric = (run) => {
      const m = run.metrics || {};
      if (m.f1 != null) return "F1 " + (+m.f1).toFixed(4);
      if (m.spearman != null) return "ρ " + (+m.spearman).toFixed(4);
      if (m.spearman_rho != null) return "ρ " + (+m.spearman_rho).toFixed(4);
      if (m.ndcg != null) return "nDCG " + (+m.ndcg).toFixed(4);
      return "—";
    };
    $("quality-eval-table").querySelector("tbody").innerHTML =
      rows.map((run) => {
        const d = run.diff || {};
        const base = d.baseline_run_id == null ? "（首条，无基线）"
          : `#${d.baseline_run_id}（${esc(d.baseline_kind || "")}）`;
        return `<tr><td>${run.id}</td>
          <td>${esc(run.eval_type)}</td>
          <td>${esc(run.dataset_version)}</td>
          <td>${esc(run.prompt_version)}</td>
          <td>${esc(run.scoring_version || "—")}</td>
          <td>${run.sample_size}</td>
          <td>${mainMetric(run)}</td>
          <td>${esc(run.verdict)}</td>
          <td>${base}</td></tr>`;
      }).join("");
  }).catch((err) => {
    $("quality-eval-note").textContent = "评测历史加载失败：" + err.message;
  });
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
  initQuality();
});
