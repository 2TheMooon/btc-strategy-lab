/* Отрисовка сайта из window.RESULTS (data.js) + window.CONTENT (content.js). */
(function () {
"use strict";
const R = window.RESULTS, C = window.CONTENT;
const $ = s => document.querySelector(s);
const el = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; };

/* ---------- форматтеры ---------- */
const pct0 = x => (x == null ? "—" : Math.round(x * 100) + "%");
const fp = x => { if (x == null) return "—"; const s = (x >= 0 ? "+" : "") + Math.round(x * 100) + "%"; return `<span class="${x >= 0 ? "pos" : "neg"}">${s}</span>`; };
const f2 = x => (x == null ? "—" : x.toFixed(2));
const cls = x => (x >= 0 ? "pos" : "neg");
const catColor = key => { const cat = (C.strategies[key] || {}).cat || "bench"; return (C.categories[cat] || {}).color || "#94a3b8"; };
const catLabel = key => { const cat = (C.strategies[key] || {}).cat || "bench"; return (C.categories[cat] || {}).label || ""; };
const paramStr = p => Object.entries(p).map(([k, v]) => `${k}=${v}`).join(", ");

/* ---------- карта цен для расчёта buy&hold на любом окне ---------- */
const priceMap = {};
R.price.dates.forEach((d, i) => priceMap[d] = R.price.close[i]);
function bhSeries(dates) {
  const base = priceMap[dates[0]];
  let last = base;
  return dates.map(d => { if (priceMap[d] != null) last = priceMap[d]; return last / base; });
}
function alignTo(baseDates, obj) { // obj={dates,values} -> values on baseDates (null если нет)
  const m = {}; obj.dates.forEach((d, i) => m[d] = obj.values[i]);
  return baseDates.map(d => (d in m ? m[d] : null));
}

/* ---------- Chart.js настройки ---------- */
Chart.defaults.color = "#9aa7bd";
Chart.defaults.font.family = "-apple-system,Segoe UI,Roboto,sans-serif";
Chart.defaults.maintainAspectRatio = false;
const GRID = "#1c2740";
function lineChart(canvas, labels, datasets, opts = {}) {
  return new Chart(canvas.getContext("2d"), {
    type: "line",
    data: { labels, datasets },
    options: {
      animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: opts.legend !== false, labels: { boxWidth: 14, font: { size: 12 } } },
        tooltip: { callbacks: opts.tip || {} } },
      scales: {
        x: { grid: { color: GRID }, ticks: { maxTicksLimit: opts.xticks || 7, autoSkip: true,
              callback: function (v) { const s = this.getLabelForValue(v); return s ? s.slice(0, 7) : s; } } },
        y: { type: opts.log ? "logarithmic" : "linear", grid: { color: GRID },
             ticks: { callback: opts.ypct ? (v => Math.round((v - 1) * 100) + "%") : (opts.yusd ? (v => "$" + (v / 1000).toFixed(0) + "k") : undefined) } },
      },
    },
  });
}

/* ================= HERO ================= */
$("#hero-sub").innerHTML = "Я прогнал классические стратегии на реальных данных биткоина и проверил их по-честному — <b>вслепую</b>. Вот что действительно работало, а что лишь красиво подгонялось под прошлое.";
const bestW = R.daily_strategies.find(s => s.key === R.best_weekly);
const bestD = R.hourly_strategies.find(s => s.key === R.best_daytrade);
const hstats = [
  ["5 лет", "период теста BTC"],
  [fp(R.buyhold.metrics.total_return), "Buy &amp; Hold"],
  [fp(bestW.walkforward.metrics.total_return), "лучшая недельная (вслепую)"],
  [fp(bestD.walkforward.metrics.total_return), "лучшая дейтрейдинг (вслепую)"],
];
$("#hero-stats").innerHTML = hstats.map(([v, l]) => `<div class="hstat"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");

/* ================= МЕТОД ================= */
$("#m-intro").innerHTML = C.sections.intro;
const lenses = C.sections.twolenses.split("<br><br>");
$("#m-fit").innerHTML = lenses[0];
$("#m-blind").innerHTML = lenses[1];
$("#m-nolook").innerHTML = C.sections.nolookahead;

/* ================= ГРАФИК BTC ================= */
let priceCh = lineChart($("#priceChart"), R.price.dates,
  [{ label: "BTC/USD", data: R.price.close, borderColor: "#f7931a", borderWidth: 1.6, pointRadius: 0,
     fill: true, backgroundColor: "rgba(247,147,26,.08)", tension: 0 }],
  { legend: false, yusd: true, tip: { label: c => "$" + Math.round(c.parsed.y).toLocaleString("ru") } });
$("#logToggle").onclick = function () {
  const log = priceCh.options.scales.y.type !== "logarithmic";
  priceCh.options.scales.y.type = log ? "logarithmic" : "linear";
  this.textContent = "Лог. шкала: " + (log ? "вкл" : "выкл");
  priceCh.update();
};
const bm = R.buyhold.metrics;
$("#bh-strip").innerHTML = [
  ["Доходность", fp(bm.total_return)], ["Годовая (CAGR)", fp(bm.cagr)],
  ["Коэф. Шарпа", f2(bm.sharpe)], ["Макс. просадка", fp(bm.max_drawdown)],
].map(([l, v]) => `<div class="chip">${l}<b>${v}</b></div>`).join("");

/* ================= ЛУЧШИЕ СТРАТЕГИИ ================= */
function featCard(s, kind, color) {
  const wf = s.walkforward.metrics, ins = s.insample.metrics;
  const card = el("div", "card feat");
  const folds = s.walkforward.folds;
  const fcount = {}; folds.forEach(f => { const k = paramStr(f.params); fcount[k] = (fcount[k] || 0) + 1; });
  const topParams = Object.entries(fcount).sort((a, b) => b[1] - a[1])[0][0];
  card.innerHTML = `
    <div class="feat-h">
      <h3>${s.name}</h3>
      <span class="badge" style="background:${color}22;color:${color};border:1px solid ${color}55">${kind}</span>
    </div>
    <div class="params">walk-forward выбирал: ${topParams}</div>
    <div class="mini-metrics">
      <div class="mm"><div class="v ${cls(wf.total_return)}">${(wf.total_return>=0?"+":"")+Math.round(wf.total_return*100)}%</div><div class="l">доходность вслепую</div></div>
      <div class="mm"><div class="v">${f2(wf.sharpe)}</div><div class="l">Шарп</div></div>
      <div class="mm"><div class="v neg">${Math.round(wf.max_drawdown*100)}%</div><div class="l">макс. просадка</div></div>
    </div>
    <div class="cmp-row">
      <span>Подгонка: <span class="vfit">${fp(ins.total_return)}</span> (Шарп ${f2(ins.sharpe)})</span> ·
      <span>Вслепую: <span class="vblind">${fp(wf.total_return)}</span> (Шарп ${f2(wf.sharpe)})</span>
    </div>
    <div class="cmp-row">Сделок: ${wf.num_trades} · Винрейт ${pct0(wf.win_rate)} · Profit factor ${f2(wf.profit_factor)} · в рынке ${pct0(wf.exposure)}</div>
    <div class="chart-box"><canvas></canvas></div>`;
  const eq = s.walkforward.equity;
  const bh = bhSeries(eq.dates);
  setTimeout(() => lineChart(card.querySelector("canvas"), eq.dates, [
    { label: "Стратегия (вслепую)", data: eq.values, borderColor: color, borderWidth: 2, pointRadius: 0, tension: 0 },
    { label: "BTC «купи и держи»", data: bh, borderColor: "#64748b", borderWidth: 1.4, borderDash: [5, 4], pointRadius: 0, tension: 0 },
  ], { ypct: true, xticks: 6 }), 0);
  return card;
}
$("#best-cards").append(
  featCard(bestD, "Дейтрейдинг · часовые", "#a78bfa"),
  featCard(bestW, "Среднесрок · ~раз в неделю", "#2dd4bf"),
);

/* ================= ПОДГОНКА vs РЕАЛЬНОСТЬ ================= */
$("#of-lead").innerHTML = C.sections.overfit_lead;

/* «Чемпионы по подгонке»: лучшие, если судить нечестно по всему графику */
$("#champ-note").innerHTML = "А если судить <b>нечестно</b> — по подгонке под весь график? Вот «чемпионы» и то, что они дали вслепую. По чистой доходности лидеры подгонки — <b>пробой Боллинджера +234%</b> (дневные) и <b>канал Дончиана +204%</b> (часовые); по риску (Шарпу) — карточки ниже.";
const pctTxt = x => (x >= 0 ? "+" : "") + Math.round(x * 100) + "%";
function champCard(s, kind) {
  const ins = s.insample.metrics, wf = s.walkforward.metrics;
  const drop = Math.round((ins.total_return - wf.total_return) * 100);
  const note = wf.total_return < ins.total_return
    ? `Красивее всех на истории. Но вслепую доходность упала с <b style="color:#f59e0b">${pctTxt(ins.total_return)}</b> до <b style="color:#2dd4bf">${pctTxt(wf.total_return)}</b> (−${drop} п.п.) — это и есть переоптимизация.`
    : `Редкий случай: стратегия удержала результат и вслепую (${pctTxt(wf.total_return)}). Значит, дело не в подгонке, а в реальной закономерности.`;
  const card = el("div", "card");
  card.innerHTML = `
    <div class="card-tag">Чемпион по подгонке · ${kind}</div>
    <h3>${s.name.split(" (")[0]}</h3>
    <div class="params">параметры подгонки: ${paramStr(s.insample.params)}</div>
    <div class="mini-metrics">
      <div class="mm"><div class="v" style="color:#f59e0b">${pctTxt(ins.total_return)}</div><div class="l">доходность · подгонка</div></div>
      <div class="mm"><div class="v" style="color:#2dd4bf">${pctTxt(wf.total_return)}</div><div class="l">доходность · вслепую</div></div>
      <div class="mm"><div class="v"><span style="color:#f59e0b">${f2(ins.sharpe)}</span> → <span style="color:#2dd4bf">${f2(wf.sharpe)}</span></div><div class="l">Шарп: подгонка→вслепую</div></div>
    </div>
    <p class="cap">${note}</p>`;
  return card;
}
$("#podgonka-champs").append(
  champCard(R.daily_strategies.find(s => s.key === R.best_weekly_insample), "среднесрок"),
  champCard(R.hourly_strategies.find(s => s.key === R.best_daytrade_insample), "дейтрейдинг"),
);

let overfitCh = null;
function drawOverfit(tf) {
  const list = tf === "daily" ? R.daily_strategies : R.hourly_strategies;
  const labels = list.map(s => s.name.split(" (")[0]);
  const insS = list.map(s => +s.insample.metrics.sharpe.toFixed(2));
  const wfS = list.map(s => +s.walkforward.metrics.sharpe.toFixed(2));
  if (overfitCh) overfitCh.destroy();
  overfitCh = new Chart($("#overfitChart").getContext("2d"), {
    type: "bar",
    data: { labels, datasets: [
      { label: "Подгонка (in-sample)", data: insS, backgroundColor: "rgba(245,158,11,.45)", borderColor: "#f59e0b", borderWidth: 1 },
      { label: "Вслепую (walk-forward)", data: wfS, backgroundColor: "rgba(45,212,191,.75)", borderColor: "#2dd4bf", borderWidth: 1 },
    ] },
    options: { animation: false, maintainAspectRatio: false,
      plugins: { legend: { labels: { boxWidth: 14 } }, tooltip: {} },
      scales: { x: { grid: { display: false }, ticks: { maxRotation: 50, minRotation: 30, font: { size: 11 } } },
        y: { grid: { color: GRID }, title: { display: true, text: "Коэффициент Шарпа" } } } },
  });
}
drawOverfit("daily");

/* кнопки переключения добавим в заголовок секции overfit */
(function () {
  const tabs = el("div", "tabs"); tabs.style.marginBottom = "8px";
  tabs.innerHTML = `<button class="tab active" data-tf="daily">Среднесрок (дневные)</button><button class="tab" data-tf="hourly">Дейтрейдинг (часовые)</button>`;
  $("#overfit .chart-box").before(tabs);
  tabs.querySelectorAll(".tab").forEach(b => b.onclick = () => {
    tabs.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
    b.classList.add("active"); drawOverfit(b.dataset.tf);
  });
})();

/* ================= КАРТА ПОДГОНКИ (HEATMAP) ================= */
$("#surf-note").innerHTML = C.sections.surface_note;
(function () {
  const data = R.sma_surface;
  const fasts = [...new Set(data.map(d => d.fast))].sort((a, b) => a - b);
  const slows = [...new Set(data.map(d => d.slow))].sort((a, b) => a - b);
  const map = {}; data.forEach(d => map[d.fast + "_" + d.slow] = d);
  const vals = data.map(d => d.sharpe);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const best = data.reduce((a, b) => (b.sharpe > a.sharpe ? b : a));
  function color(v) {
    const t = (v - lo) / (hi - lo + 1e-9);
    const stops = [[30, 58, 138], [14, 165, 164], [250, 204, 21], [239, 68, 68]];
    const x = t * 3, i = Math.min(2, Math.floor(x)), f = x - i;
    const c = stops[i].map((s, k) => Math.round(s + (stops[i + 1][k] - s) * f));
    return `rgb(${c[0]},${c[1]},${c[2]})`;
  }
  const t = el("table", "heat");
  let head = "<tr><th>fast \\ slow</th>" + slows.map(s => `<th>${s}</th>`).join("") + "</tr>";
  let body = fasts.map(fa => "<tr><th>" + fa + "</th>" + slows.map(sl => {
    const d = map[fa + "_" + sl];
    if (!d) return `<td style="background:#0c121d;color:#33405a">·</td>`;
    const isBest = d === best;
    return `<td class="${isBest ? "best" : ""}" style="background:${color(d.sharpe)}" title="fast=${fa}, slow=${sl}\nШарп=${d.sharpe.toFixed(2)}, доход=${Math.round(d.total_return*100)}%">${d.sharpe.toFixed(2)}</td>`;
  }).join("") + "</tr>").join("");
  t.innerHTML = head + body;
  $("#heatmap").append(t);
  $("#heatmap").after(el("p", "cap", `Самая яркая клетка (обведена белым) — fast=${best.fast}, slow=${best.slow}, Шарп ${best.sharpe.toFixed(2)}, доход ${Math.round(best.total_return*100)}%. Именно её выбрала бы «подгонка». Но посмотрите, как резко меняется цвет у соседей — стратегия держится на удачном попадании, а не на устойчивой закономерности.`));
})();

/* ================= WALK-FORWARD ШАГИ ================= */
$("#wf-lead").innerHTML = C.sections.foldsplain;
(function () {
  const s = bestW; const folds = s.walkforward.folds;
  $("#wf-pick").innerHTML = `Пример — лучшая недельная стратегия <b>${s.name}</b>. На каждом полугодии параметры заново подбираются по прошлому, затем торгуются на следующем, не виденном куске.`;
  const labels = folds.map(f => f.start_date.slice(0, 7));
  const exp = folds.map(f => f.train_sharpe != null ? +f.train_sharpe.toFixed(2) : null);
  const real = folds.map(f => +f.test_sharpe.toFixed(2));
  new Chart($("#foldChart").getContext("2d"), {
    type: "bar",
    data: { labels, datasets: [
      { label: "Ожидание (на обучении)", data: exp, backgroundColor: "rgba(245,158,11,.5)", borderColor: "#f59e0b", borderWidth: 1 },
      { label: "Реальность (вслепую)", data: real, backgroundColor: "rgba(45,212,191,.8)", borderColor: "#2dd4bf", borderWidth: 1 },
    ] },
    options: { animation: false, maintainAspectRatio: false,
      plugins: { legend: { labels: { boxWidth: 14 } } },
      scales: { x: { grid: { display: false } }, y: { grid: { color: GRID }, title: { display: true, text: "Коэф. Шарпа на окне" } } } },
  });
  const tbl = $("#foldTable");
  tbl.innerHTML = "<thead><tr><th>Окно (вслепую)</th><th>Параметры</th><th>Доходность</th><th>Шарп</th></tr></thead><tbody>" +
    folds.map(f => `<tr><td>${f.start_date} → ${f.end_date}</td><td style="font-family:monospace;font-size:12px">${paramStr(f.params)}</td><td class="${cls(f.test_return)}">${(f.test_return>=0?"+":"")+Math.round(f.test_return*100)}%</td><td>${f.test_sharpe.toFixed(2)}</td></tr>`).join("") + "</tbody>";
})();

/* ================= ГАЛЕРЕЯ ================= */
const galleryNote = { daily: C.sections.weekly_note, hourly: C.sections.daytrade_note };
function metricRows(ins, wf) {
  const rows = [
    ["Итоговая доходность", fp(ins.total_return), fp(wf.total_return)],
    ["Годовая (CAGR)", fp(ins.cagr), fp(wf.cagr)],
    ["Коэф. Шарпа", f2(ins.sharpe), f2(wf.sharpe)],
    ["Макс. просадка", fp(ins.max_drawdown), fp(wf.max_drawdown)],
    ["Сделок", ins.num_trades, wf.num_trades],
    ["Винрейт", pct0(ins.win_rate), pct0(wf.win_rate)],
    ["Profit factor", f2(ins.profit_factor), f2(wf.profit_factor)],
  ];
  return "<table class='cmp-table'><thead><tr><th>Метрика</th><th class='h-fit'>Подгонка</th><th class='h-blind'>Вслепую</th></tr></thead><tbody>" +
    rows.map(r => `<tr><td>${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td></tr>`).join("") + "</tbody></table>";
}
function gCard(s) {
  const info = C.strategies[s.key] || {};
  const color = catColor(s.key);
  const card = el("div", "gcard");
  const pros = (info.pros || []).map(x => `<li>${x}</li>`).join("");
  const cons = (info.cons || []).map(x => `<li>${x}</li>`).join("");
  card.innerHTML = `
    <div class="gh"><h3>${s.name}</h3>
      <span class="tag-cat" style="background:${color}">${catLabel(s.key)}</span></div>
    <div class="formula">${info.math || s.formula}</div>
    <div class="idea">${info.idea || ""}</div>
    <div class="proscons">
      <div><div class="pc-h ph-pro">Плюсы</div><ul>${pros}</ul></div>
      <div><div class="pc-h ph-con">Минусы</div><ul>${cons}</ul></div>
    </div>
    ${metricRows(s.insample.metrics, s.walkforward.metrics)}
    <div class="spark"><canvas></canvas></div>`;
  const eq = s.walkforward.equity, bh = bhSeries(eq.dates);
  setTimeout(() => lineChart(card.querySelector(".spark canvas"), eq.dates, [
    { label: "Вслепую", data: eq.values, borderColor: color, borderWidth: 2, pointRadius: 0, tension: 0 },
    { label: "Buy&Hold", data: bh, borderColor: "#64748b", borderWidth: 1.3, borderDash: [4, 4], pointRadius: 0, tension: 0 },
  ], { ypct: true, xticks: 5, legend: true }), 0);
  return card;
}
function renderGallery(tf) {
  const grid = $("#gallery-grid"); grid.innerHTML = "";
  $("#gallery-note").innerHTML = galleryNote[tf];
  const list = (tf === "daily" ? R.daily_strategies : R.hourly_strategies).slice()
    .sort((a, b) => b.walkforward.metrics.sharpe - a.walkforward.metrics.sharpe);
  list.forEach(s => grid.append(gCard(s)));
}
document.querySelectorAll("#gallery .tab").forEach(b => b.onclick = () => {
  document.querySelectorAll("#gallery .tab").forEach(x => x.classList.remove("active"));
  b.classList.add("active"); renderGallery(b.dataset.tf);
});
renderGallery("daily");

/* ================= СВОДНАЯ ТАБЛИЦА ================= */
(function () {
  const rows = [];
  rows.push({ name: "Buy & Hold", key: "buyhold", tf: "—", m: R.buyhold.metrics, ins: R.buyhold.metrics });
  R.daily_strategies.forEach(s => rows.push({ name: s.name.split(" (")[0], key: s.key, tf: "дневные", m: s.walkforward.metrics, ins: s.insample.metrics }));
  R.hourly_strategies.forEach(s => rows.push({ name: s.name.split(" (")[0], key: s.key, tf: "часовые", m: s.walkforward.metrics, ins: s.insample.metrics }));
  const cols = [
    ["Стратегия", r => `<span class="tag-cat" style="background:${catColor(r.key)};margin-right:6px">&nbsp;</span>${r.name}`, null],
    ["ТФ", r => r.tf, r => r.tf],
    ["Доходность", r => fp(r.m.total_return), r => r.m.total_return],
    ["CAGR", r => fp(r.m.cagr), r => r.m.cagr],
    ["Шарп", r => f2(r.m.sharpe), r => r.m.sharpe],
    ["Просадка", r => fp(r.m.max_drawdown), r => r.m.max_drawdown],
    ["Сделок", r => r.m.num_trades, r => r.m.num_trades],
    ["Винрейт", r => pct0(r.m.win_rate), r => r.m.win_rate],
    ["Шарп подгонки", r => `<span style="color:#f59e0b">${f2(r.ins.sharpe)}</span>`, r => r.ins.sharpe],
  ];
  const tbl = $("#bigTable");
  let sortI = 4, sortDir = -1;
  function render() {
    const sorted = rows.slice();
    const acc = cols[sortI][2];
    if (acc) sorted.sort((a, b) => { const x = acc(a), y = acc(b); return (x > y ? 1 : x < y ? -1 : 0) * sortDir; });
    tbl.innerHTML = "<thead><tr>" + cols.map((c, i) => `<th data-i="${i}">${c[0]}${i === sortI ? (sortDir < 0 ? " ▾" : " ▴") : ""}</th>`).join("") + "</tr></thead><tbody>" +
      sorted.map(r => "<tr>" + cols.map(c => `<td>${c[1](r)}</td>`).join("") + "</tr>").join("") + "</tbody>";
    tbl.querySelectorAll("th").forEach(th => th.onclick = () => {
      const i = +th.dataset.i; if (!cols[i][2]) return;
      if (i === sortI) sortDir *= -1; else { sortI = i; sortDir = -1; } render();
    });
  }
  render();
})();

/* ================= ЖИВАЯ ТОРГОВЛЯ (ПЕЙПЕР-ТРЕЙДИНГ) ================= */
if (window.PAPER) {
  const P = window.PAPER;
  const cap = P.start_capital;
  const money = v => (v >= 0 ? "+" : "−") + "$" + Math.abs(Math.round(v)).toLocaleString("ru");
  const pctS = x => (x == null ? "—" : (x >= 0 ? "+" : "") + (x * 100).toFixed(1) + "%");
  const sname = s => (s.label.split(" · ")[1] || s.label);

  $("#paper-lead").innerHTML = `Три стратегии торгуют BTC параллельно, по <b>$${cap.toLocaleString("ru")}</b> на каждую. ` +
    `Живой форвард-тест запущен <b>${P.start_date}</b> — таблицы наполняются по мере появления сигналов. ` +
    `Текущая цена BTC: <b>$${Math.round(P.current_price).toLocaleString("ru")}</b>.`;
  const anyOpen = P.strategies.some(s => s.summary.position);
  $("#paper-warn").innerHTML = `⚠️ <b>Бумажная торговля (симуляция)</b>, реальные ордера не выставляются. ` +
    (anyOpen ? "" : "Сейчас все стратегии <b>в кэше</b>: трендовые системы защитно вышли из падающего рынка. Как только сработает сигнал на покупку — здесь появится открытая сделка. ") +
    `Обновлено: ${P.last_run} · свечи: дневная ${P.last_daily_close}, часовая ${P.last_hourly_close}.`;

  const pcard = (s, isBench) => {
    const sm = s.summary, r = sm.total_return;
    const pos = isBench
      ? '<span class="dot in"></span>в рынке (эталон)'
      : (sm.position ? '<span class="dot in"></span>в рынке' : '<span class="dot out"></span>в кэше');
    const extra = isBench
      ? `<div class="prow"><span class="pill">${pos}</span><span class="pill">вход $${Math.round(s.entry_price).toLocaleString("ru")}</span></div>`
      : `<div class="prow"><span class="pill">${pos}</span><span class="pill">закрытых: ${sm.closed_trades}</span>${sm.win_rate != null ? `<span class="pill">винрейт ${Math.round(sm.win_rate * 100)}%</span>` : ""}</div>
         <div class="prow"><span class="pill" style="border-color:${s.color}55">${s.tf} · ${s.stop_desc}</span></div>`;
    return `<div class="pcard" style="border-top-color:${s.color}">
      <div class="pk" style="color:${s.color}">${isBench ? "эталон" : s.kind}</div>
      <h3>${isBench ? s.label : sname(s)}</h3>
      <div class="pret ${r >= 0 ? "pos" : "neg"}">${pctS(r)}</div>
      <div class="peq">профит ${money(sm.total_pnl)} · капитал $${Math.round(sm.equity).toLocaleString("ru")}</div>
      ${extra}</div>`;
  };
  $("#paper-cards").innerHTML = P.strategies.map(s => pcard(s, false)).join("") + pcard(P.benchmark, true);

  // открытые сделки
  const openRows = P.strategies.filter(s => s.open_trade).map(s => {
    const o = s.open_trade;
    const stop = o.stop_price != null ? `$${Math.round(o.stop_price).toLocaleString("ru")} (${(o.stop_pct * 100).toFixed(1)}%)` : "—";
    return `<tr><td><span class="dot in"></span>${sname(s)}</td><td>${o.entry_ts.replace("T", " ")}</td>` +
      `<td>$${Math.round(o.entry_price).toLocaleString("ru")}</td><td>$${Math.round(o.current_price).toLocaleString("ru")}</td>` +
      `<td class="${o.unreal_ret >= 0 ? "pos" : "neg"}">${pctS(o.unreal_ret)} (${money(o.unreal_pnl)})</td><td>${stop}</td></tr>`;
  }).join("");
  $("#openTable").innerHTML = openRows
    ? `<thead><tr><th>Стратегия</th><th>Вход (UTC)</th><th>Цена входа</th><th>Тек. цена</th><th>Нереализ. P&L</th><th>Стоп-лосс</th></tr></thead><tbody>${openRows}</tbody>`
    : `<thead><tr><th>Стратегия</th><th>Статус</th></tr></thead><tbody>` +
      P.strategies.map(s => `<tr><td>${sname(s)}</td><td><span class="dot out"></span>в кэше — ждёт сигнала на покупку</td></tr>`).join("") + `</tbody>`;

  // график капитала (растёт с каждым запуском рутины)
  const series = P.strategies.map(s => ({ label: s.kind, color: s.color, hist: s.equity, dash: false }))
    .concat([{ label: "купи и держи", color: "#64748b", hist: P.benchmark.equity || [], dash: true }]);
  const allTs = (series[0].hist || []).map(p => p.t);
  if (allTs.length >= 1) {
    const ds = series.map(s => {
      const m = {}; (s.hist || []).forEach(p => m[p.t] = p.e);
      return { label: s.label, data: allTs.map(t => (t in m ? m[t] : null)),
        borderColor: s.color, borderWidth: s.dash ? 1.5 : 2.2, borderDash: s.dash ? [5, 4] : [],
        pointRadius: allTs.length <= 4 ? 3 : 0, tension: 0 };
    });
    lineChart($("#paperChart"), allTs.map(t => t.slice(5, 16).replace("T", " ")), ds,
      { yusd: true, xticks: 6, tip: { label: c => c.dataset.label + ": $" + Math.round(c.parsed.y).toLocaleString("ru") } });
  }

  $("#paper-meta").innerHTML = [
    ["Старт", P.start_date], ["Капитал / стратегию", "$" + cap.toLocaleString("ru")],
    ["Комиссия", (P.fee * 100) + "% / сделка"], ["Дончиан", P.donchian_n + "ч · стоп " + P.atr_k + "×ATR(" + P.atr_n + ")"],
  ].map(([l, v]) => `<div class="chip">${l}<b>${v}</b></div>`).join("");

  // журнал закрытых сделок
  let trows = "";
  P.strategies.forEach(s => s.trades.forEach(t => {
    trows += `<tr><td>${sname(s)}</td><td>${t.entry_ts.replace("T", " ")}</td><td>$${Math.round(t.entry_price).toLocaleString("ru")}</td>` +
      `<td>${t.exit_ts.replace("T", " ")}</td><td>$${Math.round(t.exit_price).toLocaleString("ru")}</td>` +
      `<td class="${t.ret >= 0 ? "pos" : "neg"}">${pctS(t.ret)}</td><td class="${t.pnl >= 0 ? "pos" : "neg"}">${money(t.pnl)}</td><td>${t.reason}</td></tr>`;
  }));
  if (trows) {
    $("#tradesTable").innerHTML = `<thead><tr><th>Стратегия</th><th>Вход (UTC)</th><th>Цена</th><th>Выход</th><th>Цена</th><th>Доход</th><th>P&L</th><th>Причина</th></tr></thead><tbody>${trows}</tbody>`;
    $("#trades-empty").textContent = "";
  } else {
    $("#tradesTable").innerHTML = "";
    $("#trades-empty").textContent = "Закрытых сделок пока нет — журнал заполнится после первых выходов из позиций.";
  }
}

/* ================= ВЫВОДЫ / ДИСКЛЕЙМЕР / ФУТЕР ================= */
$("#lessons").innerHTML = C.lessons.map(([h, p]) => `<div class="lesson"><h3>${h}</h3><p>${p}</p></div>`).join("");
$("#disclaimer").innerHTML = C.disclaimer;
$("#foot-meta").innerHTML = `${R.meta.symbol} · ${R.meta.date_start} — ${R.meta.date_end} · ${R.meta.n_daily} дневных и ${R.meta.n_hourly.toLocaleString("ru")} часовых свечей`;
})();
