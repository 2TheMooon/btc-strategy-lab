/* Renders the site from window.RESULTS (data.js), window.PAPER (paper.js),
   window.I18N (i18n.js). Default language English; switcher with no flags. */
(function () {
"use strict";
const R = window.RESULTS, I18N = window.I18N, P = window.PAPER;
const $ = s => document.querySelector(s);
const el = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; };

const CATCOLOR = { trend: "#2dd4bf", meanrev: "#f59e0b", momentum: "#a78bfa", bench: "#94a3b8" };
const LOCALE = { en: "en-US", ru: "ru-RU", es: "es-ES", fr: "fr-FR", de: "de-DE", zh: "zh-CN" };
const YEARS_WORD = { en: "years", ru: "лет", es: "años", fr: "ans", de: "Jahre", zh: "年" };

let LANG = localStorage.getItem("btc_lang") || "en";
if (!I18N[LANG]) LANG = "en";
let T = I18N[LANG];
let galleryTab = "daily", overfitTab = "daily";

/* ---------- helpers ---------- */
const loc = () => LOCALE[LANG] || "en-US";
const nf = x => Number(x).toLocaleString(loc());
const tpl = (s, v) => String(s).replace(/\{(\w+)\}/g, (m, k) => (k in v ? v[k] : m));
const pct0 = x => (x == null ? "—" : Math.round(x * 100) + "%");
const pctS = x => (x == null ? "—" : (x >= 0 ? "+" : "") + (x * 100).toFixed(1) + "%");
const fp = x => { if (x == null) return "—"; return `<span class="${x >= 0 ? "pos" : "neg"}">${(x >= 0 ? "+" : "") + Math.round(x * 100)}%</span>`; };
const f2 = x => (x == null ? "—" : x.toFixed(2));
const cls = x => (x >= 0 ? "pos" : "neg");
const money = v => (v >= 0 ? "+" : "−") + "$" + nf(Math.abs(Math.round(v)));
const usd = v => "$" + nf(Math.round(v));
const paramStr = p => Object.entries(p).map(([k, v]) => `${k}=${v}`).join(", ");
const U = k => (T.ui[k] != null ? T.ui[k] : (I18N.en.ui[k] != null ? I18N.en.ui[k] : k));
const STR = key => (T.strat[key] || I18N.en.strat[key]);   // strategy content with EN fallback
const CAT = c => (T.cat[c] || I18N.en.cat[c] || c);

/* price map for buy&hold on any window */
const priceMap = {};
R.price.dates.forEach((d, i) => priceMap[d] = R.price.close[i]);
function bhSeries(dates) { const base = priceMap[dates[0]]; let last = base; return dates.map(d => { if (priceMap[d] != null) last = priceMap[d]; return last / base; }); }

/* Chart.js */
Chart.defaults.color = "#9aa7bd";
Chart.defaults.font.family = "-apple-system,Segoe UI,Roboto,sans-serif";
Chart.defaults.maintainAspectRatio = false;
const GRID = "#1c2740";
function destroyAllCharts() { document.querySelectorAll("canvas").forEach(cv => { const c = Chart.getChart(cv); if (c) c.destroy(); }); }
function lineChart(canvas, labels, datasets, opts = {}) {
  return new Chart(canvas.getContext("2d"), {
    type: "line", data: { labels, datasets },
    options: { animation: false, interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: opts.legend !== false, labels: { boxWidth: 14, font: { size: 12 } } }, tooltip: { callbacks: opts.tip || {} } },
      scales: { x: { grid: { color: GRID }, ticks: { maxTicksLimit: opts.xticks || 7, autoSkip: true, callback: function (v) { const s = this.getLabelForValue(v); return s ? String(s).slice(0, 7) : s; } } },
        y: { type: opts.log ? "logarithmic" : "linear", grid: { color: GRID }, ticks: { callback: opts.ypct ? (v => Math.round((v - 1) * 100) + "%") : (opts.yusd ? (v => "$" + (v / 1000).toFixed(0) + "k") : undefined) } } } },
  });
}

/* ================= RENDER ================= */
function render() {
  T = I18N[LANG];
  destroyAllCharts();
  document.documentElement.lang = LANG;
  document.documentElement.dir = T.dir || "ltr";

  // fill all static [data-i18n] / [data-i18n-html]
  const resolve = key => { const p = key.split("."); let o = T, e = I18N.en; for (const k of p) { o = o && o[k]; e = e && e[k]; } return (o != null ? o : e); };
  document.querySelectorAll("[data-i18n]").forEach(e => { const v = resolve(e.getAttribute("data-i18n")); if (v != null) e.textContent = v; });
  document.querySelectorAll("[data-i18n-html]").forEach(e => { const v = resolve(e.getAttribute("data-i18n-html")); if (v != null) e.innerHTML = v; });

  renderHero(); renderChart(); renderBest(); renderPaper();
  renderOverfit(); renderSurface(); renderWalkforward();
  buildTabs(); renderGallery(); renderTable(); renderLessons(); renderFooter();
}

/* ----- hero ----- */
function renderHero() {
  const bestW = R.daily_strategies.find(s => s.key === R.best_weekly);
  const bestD = R.hourly_strategies.find(s => s.key === R.best_daytrade);
  const stats = [
    [R.meta.years + " " + (YEARS_WORD[LANG] || ""), U("hs_period")],
    [fp(R.buyhold.metrics.total_return), U("hs_bh")],
    [fp(bestW.walkforward.metrics.total_return), U("hs_weekly")],
    [fp(bestD.walkforward.metrics.total_return), U("hs_daytrade")],
  ];
  $("#hero-stats").innerHTML = stats.map(([v, l]) => `<div class="hstat"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
}

/* ----- price chart ----- */
let priceLog = false;
function renderChart() {
  const ch = lineChart($("#priceChart"), R.price.dates,
    [{ label: "BTC/USD", data: R.price.close, borderColor: "#f7931a", borderWidth: 1.6, pointRadius: 0, fill: true, backgroundColor: "rgba(247,147,26,.08)", tension: 0 }],
    { legend: false, yusd: true, log: priceLog, tip: { label: c => usd(c.parsed.y) } });
  $("#logToggle").textContent = priceLog ? U("log_on") : U("log_off");
  $("#logToggle").onclick = () => { priceLog = !priceLog; ch.options.scales.y.type = priceLog ? "logarithmic" : "linear"; $("#logToggle").textContent = priceLog ? U("log_on") : U("log_off"); ch.update(); };
  const bm = R.buyhold.metrics;
  $("#bh-strip").innerHTML = [[U("m_return"), fp(bm.total_return)], [U("m_cagr"), fp(bm.cagr)], [U("m_sharpe"), f2(bm.sharpe)], [U("m_maxdd"), fp(bm.max_drawdown)]]
    .map(([l, v]) => `<div class="chip">${l}<b>${v}</b></div>`).join("");
}

/* ----- best cards ----- */
function featCard(s, badge, color) {
  const wf = s.walkforward.metrics, ins = s.insample.metrics;
  const fc = {}; s.walkforward.folds.forEach(f => { const k = paramStr(f.params); fc[k] = (fc[k] || 0) + 1; });
  const topParams = Object.entries(fc).sort((a, b) => b[1] - a[1])[0][0];
  const card = el("div", "card feat");
  card.innerHTML = `
    <div class="feat-h"><h3>${STR(s.key).name}</h3>
      <span class="badge" style="background:${color}22;color:${color};border:1px solid ${color}55">${badge}</span></div>
    <div class="params">${U("feat_picked")} ${topParams}</div>
    <div class="mini-metrics">
      <div class="mm"><div class="v ${cls(wf.total_return)}">${(wf.total_return>=0?"+":"")+Math.round(wf.total_return*100)}%</div><div class="l">${U("feat_ret_blind")}</div></div>
      <div class="mm"><div class="v">${f2(wf.sharpe)}</div><div class="l">${U("m_sharpe")}</div></div>
      <div class="mm"><div class="v neg">${Math.round(wf.max_drawdown*100)}%</div><div class="l">${U("feat_maxdd")}</div></div>
    </div>
    <div class="cmp-row"><span>${U("feat_fit")} <span class="vfit">${fp(ins.total_return)}</span> (${U("m_sharpe")} ${f2(ins.sharpe)})</span> ·
      <span>${U("feat_blind")} <span class="vblind">${fp(wf.total_return)}</span> (${U("m_sharpe")} ${f2(wf.sharpe)})</span></div>
    <div class="cmp-row">${U("feat_trades")}: ${wf.num_trades} · ${U("feat_winrate")} ${pct0(wf.win_rate)} · ${U("feat_pf")} ${f2(wf.profit_factor)} · ${U("feat_inmarket")} ${pct0(wf.exposure)}</div>
    <div class="chart-box"><canvas></canvas></div>`;
  return { card, s, color };
}
function renderBest() {
  const bestW = R.daily_strategies.find(s => s.key === R.best_weekly);
  const bestD = R.hourly_strategies.find(s => s.key === R.best_daytrade);
  const items = [featCard(bestD, U("badge_daytrade"), "#a78bfa"), featCard(bestW, U("badge_weekly"), "#2dd4bf")];
  const host = $("#best-cards"); host.innerHTML = ""; items.forEach(it => host.append(it.card));
  items.forEach(it => { const eq = it.s.walkforward.equity; lineChart(it.card.querySelector("canvas"), eq.dates,
    [{ label: U("leg_strategy_blind"), data: eq.values, borderColor: it.color, borderWidth: 2, pointRadius: 0, tension: 0 },
     { label: U("leg_bh"), data: bhSeries(eq.dates), borderColor: "#64748b", borderWidth: 1.4, borderDash: [5, 4], pointRadius: 0, tension: 0 }], { ypct: true, xticks: 6 }); });
}

/* ----- paper (live) ----- */
function pbaseName(b) { return U("pbase_" + b); }
function stopDesc(s) { return s.has_stop ? tpl(U("stop_with"), { k: s.stop_k, n: s.stop_atr_n }) : U("stop_none"); }
function pName(s) { return pbaseName(s.base) + " · " + (s.has_stop ? U("with_stop") : U("no_stop")); }
function renderPaper() {
  if (!P) return;
  const cap = P.start_capital;
  $("#paper-lead").innerHTML = tpl(U("paper_lead"), { cap: nf(cap), date: P.start_date, price: nf(Math.round(P.current_price)) });
  $("#paper-warn").innerHTML = U("paper_warn_sim") + tpl(U("paper_warn_upd"), { utc: P.last_run_utc });

  const pcard = (s, isBench) => {
    const sm = s.summary, r = sm.total_return;
    const pos = isBench ? `<span class="dot in"></span>${U("p_inmarket")} (${U("p_bench")})`
      : (sm.position ? `<span class="dot in"></span>${U("p_inmarket")}` : `<span class="dot out"></span>${U("p_cash")}`);
    const extra = isBench
      ? `<div class="prow"><span class="pill">${pos}</span><span class="pill">${U("p_entry")} ${usd(s.entry_price)}</span></div>`
      : `<div class="prow"><span class="pill">${pos}</span><span class="pill">${U("p_closed")}: ${sm.closed_trades}</span>${sm.win_rate != null ? `<span class="pill">${U("p_winrate")} ${Math.round(sm.win_rate * 100)}%</span>` : ""}</div>
         <div class="prow"><span class="pill" style="border-color:${s.color}55">${s.tf === "hourly" ? U("tf_hourly") : U("tf_daily")} · ${stopDesc(s)}</span></div>`;
    return `<div class="pcard" style="border-top-color:${s.color}">
      <div class="pk" style="color:${s.color}">${isBench ? U("p_bench") : (s.has_stop ? U("with_stop") : U("no_stop"))}</div>
      <h3>${isBench ? U("bh_name") : pbaseName(s.base)}</h3>
      <div class="pret ${r >= 0 ? "pos" : "neg"}">${pctS(r)}</div>
      <div class="peq">${U("p_profit")} ${money(sm.total_pnl)} · ${U("p_capital")} ${usd(sm.equity)}</div>${extra}</div>`;
  };
  $("#paper-cards").innerHTML = P.strategies.map(s => pcard(s, false)).join("") + pcard(P.benchmark, true);

  const openRows = P.strategies.filter(s => s.open_trade).map(s => { const o = s.open_trade;
    const stop = o.stop_price != null ? `${usd(o.stop_price)} (${(o.stop_pct * 100).toFixed(1)}%)` : "—";
    return `<tr><td><span class="dot in"></span>${pName(s)}</td><td>${o.entry_ts.replace("T", " ")}</td><td>${usd(o.entry_price)}</td><td>${usd(o.current_price)}</td><td class="${o.unreal_ret >= 0 ? "pos" : "neg"}">${pctS(o.unreal_ret)} (${money(o.unreal_pnl)})</td><td>${stop}</td></tr>`;
  }).join("");
  $("#openTable").innerHTML = openRows
    ? `<thead><tr><th>${U("oh_strategy")}</th><th>${U("oh_entry")}</th><th>${U("oh_entry_price")}</th><th>${U("oh_cur_price")}</th><th>${U("oh_unreal")}</th><th>${U("oh_stop")}</th></tr></thead><tbody>${openRows}</tbody>`
    : `<thead><tr><th>${U("oh_strategy")}</th><th>${U("oh_status")}</th></tr></thead><tbody>` + P.strategies.map(s => `<tr><td>${pName(s)}</td><td><span class="dot out"></span>${U("open_none")}</td></tr>`).join("") + `</tbody>`;

  const series = P.strategies.map(s => ({ label: pName(s), color: s.color, hist: s.equity, dash: false }))
    .concat([{ label: U("bh_name"), color: "#64748b", hist: P.benchmark.equity || [], dash: true }]);
  const allTs = (series[0].hist || []).map(p => p.t);
  if (allTs.length >= 1) {
    const ds = series.map(s => { const m = {}; (s.hist || []).forEach(p => m[p.t] = p.e);
      return { label: s.label, data: allTs.map(t => (t in m ? m[t] : null)), borderColor: s.color, borderWidth: s.dash ? 1.5 : 2, borderDash: s.dash ? [5, 4] : [], pointRadius: allTs.length <= 4 ? 3 : 0, tension: 0 }; });
    lineChart($("#paperChart"), allTs.map(t => t.slice(5, 16).replace("T", " ")), ds, { yusd: true, xticks: 6, tip: { label: c => c.dataset.label + ": " + usd(c.parsed.y) } });
  }
  $("#paper-meta").innerHTML = [[U("c_start"), P.start_date], [U("c_capital"), usd(cap)], [U("c_fee"), (P.fee * 100) + "%"], [U("c_source"), P.data_source]]
    .map(([l, v]) => `<div class="chip">${l}<b>${v}</b></div>`).join("");

  const reason = r => (r === "stop" ? U("reason_stop") : U("reason_signal"));
  let trows = "";
  P.strategies.forEach(s => s.trades.forEach(t => {
    trows += `<tr><td>${pName(s)}</td><td>${t.entry_ts.replace("T", " ")}</td><td>${usd(t.entry_price)}</td><td>${t.exit_ts.replace("T", " ")}</td><td>${usd(t.exit_price)}</td><td class="${t.ret >= 0 ? "pos" : "neg"}">${pctS(t.ret)}</td><td class="${t.pnl >= 0 ? "pos" : "neg"}">${money(t.pnl)}</td><td>${reason(t.reason)}</td></tr>`;
  }));
  if (trows) { $("#tradesTable").innerHTML = `<thead><tr><th>${U("oh_strategy")}</th><th>${U("oh_entry")}</th><th>${U("th_price")}</th><th>${U("th_exit")}</th><th>${U("th_price")}</th><th>${U("th_ret")}</th><th>${U("th_pnl")}</th><th>${U("th_reason")}</th></tr></thead><tbody>${trows}</tbody>`; $("#trades-empty").textContent = ""; }
  else { $("#tradesTable").innerHTML = ""; $("#trades-empty").textContent = U("trades_empty"); }
}

/* ----- overfit ----- */
function champCard(s, kind) {
  const ins = s.insample.metrics, wf = s.walkforward.metrics;
  const drop = Math.round((ins.total_return - wf.total_return) * 100);
  const note = wf.total_return < ins.total_return
    ? tpl(U("champ_note_drop"), { fit: pctS(ins.total_return), blind: pctS(wf.total_return), drop })
    : tpl(U("champ_note_hold"), { blind: pctS(wf.total_return) });
  const c = el("div", "card");
  c.innerHTML = `<div class="card-tag">${tpl(U("champ_tag"), { kind })}</div>
    <h3>${STR(s.key).name}</h3>
    <div class="params">${U("champ_params")} ${paramStr(s.insample.params)}</div>
    <div class="mini-metrics">
      <div class="mm"><div class="v" style="color:#f59e0b">${pctS(ins.total_return)}</div><div class="l">${U("champ_ret_fit")}</div></div>
      <div class="mm"><div class="v" style="color:#2dd4bf">${pctS(wf.total_return)}</div><div class="l">${U("champ_ret_blind")}</div></div>
      <div class="mm"><div class="v"><span style="color:#f59e0b">${f2(ins.sharpe)}</span> → <span style="color:#2dd4bf">${f2(wf.sharpe)}</span></div><div class="l">${U("champ_sharpe_arrow")}</div></div>
    </div><p class="cap">${note}</p>`;
  return c;
}
function renderOverfit() {
  const host = $("#podgonka-champs"); host.innerHTML = "";
  host.append(champCard(R.daily_strategies.find(s => s.key === R.best_weekly_insample), U("kind_weekly")));
  host.append(champCard(R.hourly_strategies.find(s => s.key === R.best_daytrade_insample), U("kind_daytrade")));
  drawOverfitChart();
}
function drawOverfitChart() {
  const list = overfitTab === "daily" ? R.daily_strategies : R.hourly_strategies;
  const labels = list.map(s => STR(s.key).name);
  new Chart($("#overfitChart").getContext("2d"), { type: "bar",
    data: { labels, datasets: [
      { label: U("ov_leg_fit"), data: list.map(s => +s.insample.metrics.sharpe.toFixed(2)), backgroundColor: "rgba(245,158,11,.45)", borderColor: "#f59e0b", borderWidth: 1 },
      { label: U("ov_leg_blind"), data: list.map(s => +s.walkforward.metrics.sharpe.toFixed(2)), backgroundColor: "rgba(45,212,191,.75)", borderColor: "#2dd4bf", borderWidth: 1 }] },
    options: { animation: false, maintainAspectRatio: false, plugins: { legend: { labels: { boxWidth: 14 } } },
      scales: { x: { grid: { display: false }, ticks: { maxRotation: 50, minRotation: 30, font: { size: 11 } } }, y: { grid: { color: GRID }, title: { display: true, text: U("ov_ytitle") } } } } });
}

/* ----- surface heatmap ----- */
function renderSurface() {
  const data = R.sma_surface;
  const fasts = [...new Set(data.map(d => d.fast))].sort((a, b) => a - b);
  const slows = [...new Set(data.map(d => d.slow))].sort((a, b) => a - b);
  const map = {}; data.forEach(d => map[d.fast + "_" + d.slow] = d);
  const vals = data.map(d => d.sharpe), lo = Math.min(...vals), hi = Math.max(...vals);
  const best = data.reduce((a, b) => (b.sharpe > a.sharpe ? b : a));
  const color = v => { const t = (v - lo) / (hi - lo + 1e-9); const st = [[30, 58, 138], [14, 165, 164], [250, 204, 21], [239, 68, 68]]; const x = t * 3, i = Math.min(2, Math.floor(x)), f = x - i; const c = st[i].map((s, k) => Math.round(s + (st[i + 1][k] - s) * f)); return `rgb(${c[0]},${c[1]},${c[2]})`; };
  const t = el("table", "heat");
  t.innerHTML = "<tr><th>fast \\ slow</th>" + slows.map(s => `<th>${s}</th>`).join("") + "</tr>" +
    fasts.map(fa => "<tr><th>" + fa + "</th>" + slows.map(sl => { const d = map[fa + "_" + sl];
      if (!d) return `<td style="background:#0c121d;color:#33405a">·</td>`;
      return `<td class="${d === best ? "best" : ""}" style="background:${color(d.sharpe)}" title="fast=${fa}, slow=${sl}\nSharpe=${d.sharpe.toFixed(2)}, ${Math.round(d.total_return*100)}%">${d.sharpe.toFixed(2)}</td>`; }).join("") + "</tr>").join("");
  const hm = $("#heatmap"); hm.innerHTML = ""; hm.append(t);
  $("#surf-cap").innerHTML = tpl(U("surf_best_cap"), { fast: best.fast, slow: best.slow, sh: best.sharpe.toFixed(2), ret: Math.round(best.total_return * 100) + "%" });
}

/* ----- walk-forward ----- */
function renderWalkforward() {
  const s = R.daily_strategies.find(x => x.key === R.best_weekly);
  const folds = s.walkforward.folds;
  $("#wf-pick").innerHTML = tpl(U("wf_pick"), { name: STR(s.key).name });
  new Chart($("#foldChart").getContext("2d"), { type: "bar",
    data: { labels: folds.map(f => f.start_date.slice(0, 7)), datasets: [
      { label: U("fold_leg_exp"), data: folds.map(f => f.train_sharpe != null ? +f.train_sharpe.toFixed(2) : null), backgroundColor: "rgba(245,158,11,.5)", borderColor: "#f59e0b", borderWidth: 1 },
      { label: U("fold_leg_real"), data: folds.map(f => +f.test_sharpe.toFixed(2)), backgroundColor: "rgba(45,212,191,.8)", borderColor: "#2dd4bf", borderWidth: 1 }] },
    options: { animation: false, maintainAspectRatio: false, plugins: { legend: { labels: { boxWidth: 14 } } },
      scales: { x: { grid: { display: false } }, y: { grid: { color: GRID }, title: { display: true, text: U("fold_ytitle") } } } } });
  $("#foldTable").innerHTML = `<thead><tr><th>${U("foldt_window")}</th><th>${U("foldt_params")}</th><th>${U("foldt_ret")}</th><th>${U("foldt_sharpe")}</th></tr></thead><tbody>` +
    folds.map(f => `<tr><td>${f.start_date} → ${f.end_date}</td><td style="font-family:monospace;font-size:12px">${paramStr(f.params)}</td><td class="${cls(f.test_return)}">${(f.test_return>=0?"+":"")+Math.round(f.test_return*100)}%</td><td>${f.test_sharpe.toFixed(2)}</td></tr>`).join("") + "</tbody>";
}

/* ----- tabs (overfit + gallery) ----- */
function buildTabs() {
  const ot = $("#overfit-tabs"); ot.innerHTML = "";
  [["daily", U("tab_daily")], ["hourly", U("tab_hourly")]].forEach(([k, lab]) => {
    const b = el("button", "tab" + (overfitTab === k ? " active" : ""), lab);
    b.onclick = () => { overfitTab = k; ot.querySelectorAll(".tab").forEach(x => x.classList.remove("active")); b.classList.add("active"); const c = Chart.getChart($("#overfitChart")); if (c) c.destroy(); drawOverfitChart(); };
    ot.append(b);
  });
  const gt = $("#gallery-tabs"); gt.innerHTML = "";
  [["daily", U("gtab_daily")], ["hourly", U("gtab_hourly")]].forEach(([k, lab]) => {
    const b = el("button", "tab" + (galleryTab === k ? " active" : ""), lab);
    b.onclick = () => { galleryTab = k; gt.querySelectorAll(".tab").forEach(x => x.classList.remove("active")); b.classList.add("active"); renderGallery(); };
    gt.append(b);
  });
}

/* ----- gallery ----- */
function metricRows(ins, wf) {
  const rows = [[U("mr_total"), fp(ins.total_return), fp(wf.total_return)], [U("mr_cagr"), fp(ins.cagr), fp(wf.cagr)],
    [U("mr_sharpe"), f2(ins.sharpe), f2(wf.sharpe)], [U("mr_maxdd"), fp(ins.max_drawdown), fp(wf.max_drawdown)],
    [U("mr_trades"), ins.num_trades, wf.num_trades], [U("mr_winrate"), pct0(ins.win_rate), pct0(wf.win_rate)], [U("mr_pf"), f2(ins.profit_factor), f2(wf.profit_factor)]];
  return `<table class='cmp-table'><thead><tr><th>${U("cmp_metric")}</th><th class='h-fit'>${U("cmp_fit")}</th><th class='h-blind'>${U("cmp_blind")}</th></tr></thead><tbody>` +
    rows.map(r => `<tr><td>${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td></tr>`).join("") + "</tbody></table>";
}
function gCard(s) {
  const info = STR(s.key); const color = CATCOLOR[info.cat] || "#94a3b8";
  const card = el("div", "gcard");
  card.innerHTML = `<div class="gh"><h3>${info.name}</h3><span class="tag-cat" style="background:${color}">${CAT(info.cat)}</span></div>
    <div class="formula">${info.formula}</div><div class="idea">${info.idea}</div>
    <div class="proscons"><div><div class="pc-h ph-pro">${U("g_pros")}</div><ul>${info.pros.map(x => `<li>${x}</li>`).join("")}</ul></div>
      <div><div class="pc-h ph-con">${U("g_cons")}</div><ul>${info.cons.map(x => `<li>${x}</li>`).join("")}</ul></div></div>
    ${metricRows(s.insample.metrics, s.walkforward.metrics)}<div class="spark"><canvas></canvas></div>`;
  return { card, s, color };
}
function renderGallery() {
  $("#gallery-note").innerHTML = (galleryTab === "daily" ? (T.sec.weekly_note || I18N.en.sec.weekly_note) : (T.sec.daytrade_note || I18N.en.sec.daytrade_note));
  const grid = $("#gallery-grid");
  grid.querySelectorAll("canvas").forEach(cv => { const c = Chart.getChart(cv); if (c) c.destroy(); });
  grid.innerHTML = "";
  const list = (galleryTab === "daily" ? R.daily_strategies : R.hourly_strategies).slice().sort((a, b) => b.walkforward.metrics.sharpe - a.walkforward.metrics.sharpe);
  const items = list.map(gCard); items.forEach(it => grid.append(it.card));
  items.forEach(it => { const eq = it.s.walkforward.equity; lineChart(it.card.querySelector(".spark canvas"), eq.dates,
    [{ label: U("spark_blind"), data: eq.values, borderColor: it.color, borderWidth: 2, pointRadius: 0, tension: 0 },
     { label: U("spark_bh"), data: bhSeries(eq.dates), borderColor: "#64748b", borderWidth: 1.3, borderDash: [4, 4], pointRadius: 0, tension: 0 }], { ypct: true, xticks: 5 }); });
}

/* ----- big table ----- */
let sortI = 4, sortDir = -1;
function renderTable() {
  const rows = [{ name: U("bh_name"), key: "buyhold", cat: "bench", tf: "—", m: R.buyhold.metrics, ins: R.buyhold.metrics }];
  R.daily_strategies.forEach(s => rows.push({ name: STR(s.key).name, key: s.key, cat: STR(s.key).cat, tf: U("tf_daily_w"), m: s.walkforward.metrics, ins: s.insample.metrics }));
  R.hourly_strategies.forEach(s => rows.push({ name: STR(s.key).name, key: s.key, cat: STR(s.key).cat, tf: U("tf_hourly_w"), m: s.walkforward.metrics, ins: s.insample.metrics }));
  const cols = [
    [U("tc_strategy"), r => `<span class="tag-cat" style="background:${CATCOLOR[r.cat]};margin-right:6px">&nbsp;</span>${r.name}`, null],
    [U("tc_tf"), r => r.tf, r => r.tf],
    [U("tc_return"), r => fp(r.m.total_return), r => r.m.total_return],
    [U("tc_cagr"), r => fp(r.m.cagr), r => r.m.cagr],
    [U("tc_sharpe"), r => f2(r.m.sharpe), r => r.m.sharpe],
    [U("tc_maxdd"), r => fp(r.m.max_drawdown), r => r.m.max_drawdown],
    [U("tc_trades"), r => r.m.num_trades, r => r.m.num_trades],
    [U("tc_winrate"), r => pct0(r.m.win_rate), r => r.m.win_rate],
    [U("tc_sharpe_fit"), r => `<span style="color:#f59e0b">${f2(r.ins.sharpe)}</span>`, r => r.ins.sharpe],
  ];
  const tbl = $("#bigTable");
  function draw() {
    const sorted = rows.slice(); const acc = cols[sortI][2];
    if (acc) sorted.sort((a, b) => { const x = acc(a), y = acc(b); return (x > y ? 1 : x < y ? -1 : 0) * sortDir; });
    tbl.innerHTML = "<thead><tr>" + cols.map((c, i) => `<th data-i="${i}">${c[0]}${i === sortI ? (sortDir < 0 ? " ▾" : " ▴") : ""}</th>`).join("") + "</tr></thead><tbody>" +
      sorted.map(r => "<tr>" + cols.map(c => `<td>${c[1](r)}</td>`).join("") + "</tr>").join("") + "</tbody>";
    tbl.querySelectorAll("th").forEach(th => th.onclick = () => { const i = +th.dataset.i; if (!cols[i][2]) return; if (i === sortI) sortDir *= -1; else { sortI = i; sortDir = -1; } draw(); });
  }
  draw();
}

/* ----- lessons / footer ----- */
function renderLessons() { $("#lessons").innerHTML = (T.lessons || I18N.en.lessons).map(([h, p]) => `<div class="lesson"><h3>${h}</h3><p>${p}</p></div>`).join(""); }
function renderFooter() { $("#foot-meta").innerHTML = tpl(U("foot_meta"), { sym: R.meta.symbol, start: R.meta.date_start, end: R.meta.date_end, nd: R.meta.n_daily, nh: nf(R.meta.n_hourly) }); }

/* ----- language switcher ----- */
function buildSwitcher() {
  const sel = $("#langSelect");
  sel.innerHTML = Object.keys(I18N).map(k => `<option value="${k}"${k === LANG ? " selected" : ""}>${I18N[k].name}</option>`).join("");
  sel.onchange = () => { LANG = sel.value; localStorage.setItem("btc_lang", LANG); render(); };
}

buildSwitcher();
render();
})();
