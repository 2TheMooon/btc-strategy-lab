# BTC Strategy Lab — choosing a trading strategy for Bitcoin over 5 years

A study of which classic strategies actually worked on BTC over 5 years, and how
"a pretty fit to the chart" differs from the honest "blind" result.

## 🌐 Live demo

**→ https://2themooon.github.io/btc-strategy-lab/**

The site runs 24/7: a cloud routine (GitHub Actions) updates the live paper trading
**every hour** and publishes the site to GitHub Pages — no need to keep a computer on.
The site has a language switcher (English default; EN, RU, ES, FR, DE, 中文).

## Open the site locally

Just **double-click `site/index.html`** — it works offline, no server, no internet
(data is embedded in `site/data.js` and `site/paper.js`, Chart.js is bundled locally).

Or run a local server:
```
python -m http.server 8777 --directory site
```
and open http://localhost:8777

## What the site contains

1. **Bitcoin over 5 years** (with a log-scale toggle).
2. **Best strategies** — separately for day trading (hourly candles) and medium-term
   (daily, ~one trade every 1–2 weeks). Winners are chosen by the honest out-of-sample test.
3. **📡 Live trading** — six strategies paper-trading BTC in parallel (see below).
4. **Fitting vs Reality** — the key chart: Sharpe when fitted to the whole chart vs the
   walk-forward result. Shows overfitting at a glance.
5. **Fitting map** — a heatmap of moving-average-cross parameters.
6. **Walk-forward, step by step** — how a strategy is laid onto the chart blind.
7. **All strategies** — the maths of each one, the idea in plain words, pros/cons and
   two result columns (fitting / blind).
8. **Summary table** (sortable) and **takeaways**.

## Two ways of testing (the core idea)

- **Fitting (in-sample).** Parameters are chosen over the *whole* 5-year history and scored
  on it. As if we knew the future. Pretty numbers — but a deception.
- **Blind / walk-forward (out-of-sample).** Parameters are tuned on the *past*, then traded
  on the next *unseen* slice, step by step. This is the real result.

The engine has no lookahead: the position is decided at a bar's close from data available
only up to that point, the return is earned on the next bar. A 0.1% fee per trade is included.

## Headline results (out-of-sample)

| | Best strategy | Return | Sharpe | Max drawdown |
|---|---|---|---|---|
| Medium-term (daily) | **MACD** 12/26/9 | +154% | 1.16 | −28% |
| Day trading (hourly) | **Donchian channel** | +191% | 0.95 | — |
| Benchmark | Buy & Hold | +84% | 0.50 | −77% |

Takeaways: trend strategies consistently beat the market on a risk-adjusted basis;
mean-reversion strategies fit beautifully but lose out of sample; most day-trading strategies
are eaten by fees; fewer parameters = more robustness.

## Live paper trading (📡 section on the site)

`paper_trade.py` runs a live forward-test of **six strategies** on BTC ($10,000 each),
in two variants — **with** and **without** a stop-loss — and writes open trades, the
closed-trade log and total profit to `site/paper.js`:

- **Momentum** 30/10% (daily) — no stop / ATR stop
- **MACD** 12/26/9 (daily) — no stop / ATR stop
- **Donchian** 48h breakout (hourly) — no stop / ATR stop (2.5×ATR(24))
- plus a Buy & Hold benchmark

The forward-test starts **from the day it is first run** (the start date is frozen in
`paper_state.json`). Entries/exits use the current price on a signal change; the Donchian
variant also checks the stop-loss against hourly lows. Logic is covered by `test_paper.py`.

> This is **paper trading (simulation)** — no real exchange orders are placed.

### Where it runs 24/7

The cloud engine is **GitHub Actions** (`.github/workflows/paper.yml`): every hour it runs
`paper_trade.py`, commits the fresh `paper_state.json`/`paper.js` and deploys the site to
GitHub Pages. The data source is `data-api.binance.vision` with a Kraken fallback (in case
of cloud IP geo-blocks). The local Windows Task Scheduler job is not used.

## Project structure

```
fetch_data.py   — download 5y of BTC/USDT from Binance (daily + hourly) -> data/
engine.py       — indicators, no-lookahead backtest engine, metrics, trades
optimize.py     — fitting (grid search) and walk-forward (out-of-sample)
run_all.py      — run all strategies -> results.json
build_site.py   — results.json -> site/data.js
paper_trade.py  — live paper trading -> site/paper.js   (test_paper.py = self-test)
site/           — the site (index.html, style.css, app.js, i18n.js, data.js, paper.js, vendor/)
.github/workflows/paper.yml — hourly cloud routine + Pages deploy
```

## Rebuild the backtest from scratch

```
python fetch_data.py     # refresh data (needs internet)
python run_all.py        # run strategies, rebuild results.json
python build_site.py     # update site/data.js
```

Run the live routine manually: `python paper_trade.py` · self-test: `python test_paper.py`
(to start over, delete `paper_state.json`).

## ⚠️ Disclaimer

This is research and educational material, not investment advice. Past results do not
guarantee future ones. A backtest is a simplification. Do not trade money you are not
ready to lose.
