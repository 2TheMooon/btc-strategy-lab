"""
LIVE paper trading (simulation, NOT real orders) — starts from today.

Six strategies trade BTC in parallel, $10,000 each, in two variants (no stop / with stop)
so we can compare whether a stop-loss helps or hurts:
  momentum  (daily)   Momentum 30 / 10%         — no stop  /  ATR stop
  macd      (daily)   MACD 12/26/9              — no stop  /  ATR stop
  donchian  (hourly)  Donchian 48h breakout    — no stop  /  ATR stop
Plus a Buy & Hold benchmark (since start).

State is kept incrementally (paper_state.json): position, open trade, closed-trade log,
equity curve. On every run the routine:
  - fetches fresh closed candles and the current price;
  - checks the stop-loss (against the lows of the bars since entry, on the strategy timeframe);
  - reconciles the position with the current signal, opening/closing at the current price;
  - writes open trades, the trade log and total profit to site/paper.js (site section).

Display text is localized on the site (i18n); here we only emit stable keys and numbers.

IMPORTANT: no real exchange orders are placed. This is a simulation.
"""
import sys
import os
import json
import time
import datetime
import urllib.request
import urllib.parse

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd
from engine import st_momentum, st_macd, st_donchian, atr

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "paper_state.json")
OUT_JS = os.path.join(HERE, "site", "paper.js")
SCHEMA = 4

FEE = 0.001
CAPITAL = 10000.0
DONCHIAN_N = 48

# base, timeframe, stop on/off, color, signal fn, (atr period, atr multiple) for the stop
STRATS = [
    {"key": "mom",    "base": "momentum", "tf": "daily",  "stop": False, "color": "#f59e0b",
     "fn": lambda df: st_momentum(df, 30, 0.10)},
    {"key": "mom_s",  "base": "momentum", "tf": "daily",  "stop": True,  "color": "#fbbf24",
     "fn": lambda df: st_momentum(df, 30, 0.10), "atr_n": 14, "k": 3.0},
    {"key": "macd",   "base": "macd",     "tf": "daily",  "stop": False, "color": "#2dd4bf",
     "fn": lambda df: st_macd(df, 12, 26, 9)},
    {"key": "macd_s", "base": "macd",     "tf": "daily",  "stop": True,  "color": "#5eead4",
     "fn": lambda df: st_macd(df, 12, 26, 9), "atr_n": 14, "k": 3.0},
    {"key": "don",    "base": "donchian", "tf": "hourly", "stop": False, "color": "#a78bfa",
     "fn": lambda df: st_donchian(df, DONCHIAN_N)},
    {"key": "don_s",  "base": "donchian", "tf": "hourly", "stop": True,  "color": "#c4b5fd",
     "fn": lambda df: st_donchian(df, DONCHIAN_N), "atr_n": 24, "k": 2.5},
]

# Data sources with fallback: Binance often geo-blocks cloud IPs (US), so we try the
# data-vision mirror, then the main Binance, then Kraken.
BINANCE_HOSTS = ["https://data-api.binance.vision", "https://api.binance.com", "https://api.binance.us"]
SOURCE = {"name": "?"}


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _binance_klines(interval, limit):
    for host in BINANCE_HOSTS:
        try:
            u = host + "/api/v3/klines?" + urllib.parse.urlencode(
                {"symbol": "BTCUSDT", "interval": interval, "limit": limit})
            raw = _get(u)
            if isinstance(raw, list) and raw:
                SOURCE["name"] = host.split("//")[1]
                return raw
        except Exception as e:
            print(f"  {host} klines fail: {e}")
    return None


def _kraken_klines(interval):
    mins = 1440 if interval == "1d" else 60
    d = _get(f"https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval={mins}")
    res = d["result"]
    key = [k for k in res if k != "last"][0]
    out = []
    for r in res[key]:  # [time, o, h, l, c, vwap, vol, count]
        t = int(r[0]) * 1000
        out.append([t, r[1], r[2], r[3], r[4], r[6], t + mins * 60 * 1000 - 1])
    SOURCE["name"] = "kraken"
    return out


def klines(interval, limit):
    raw = _binance_klines(interval, limit)
    if raw is None:
        print("  -> fallback Kraken")
        raw = _kraken_klines(interval)
    now = int(time.time() * 1000)
    raw = [k for k in raw if int(k[6]) < now]  # closed candles only
    df = pd.DataFrame({
        "time": [int(k[0]) for k in raw],
        "open": [float(k[1]) for k in raw], "high": [float(k[2]) for k in raw],
        "low": [float(k[3]) for k in raw], "close": [float(k[4]) for k in raw],
    })
    df["dt"] = pd.to_datetime(df["time"], unit="ms")
    return df.set_index("dt").sort_index()


def ticker_price():
    for host in BINANCE_HOSTS:
        try:
            return float(_get(host + "/api/v3/ticker/price?symbol=BTCUSDT")["price"])
        except Exception:
            continue
    d = _get("https://api.kraken.com/0/public/Ticker?pair=XBTUSD")
    res = d["result"]
    return float(res[list(res)[0]]["c"][0])


def new_strat_state():
    return {"cash": CAPITAL, "units": 0.0, "position": 0, "armed": True,
            "open_trade": None, "trades": [], "equity": [], "last_signal": 0}


def step(st, cfg, dfd, dfh, cur_px, now_utc):
    """One live step for a single strategy (no lookahead)."""
    df = dfh if cfg["tf"] == "hourly" else dfd
    sig = int(cfg["fn"](df).reindex(df.index).fillna(0.0).clip(0, 1).iloc[-1])
    now_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%S")

    def close_trade(exit_px, exit_iso, reason):
        ot = st["open_trade"]
        proceeds = st["units"] * exit_px * (1 - FEE)
        ret = proceeds / ot["entry_equity"] - 1.0
        pnl = proceeds - ot["entry_equity"]
        st["trades"].append({
            "entry_ts": ot["entry_ts"], "entry_price": round(ot["entry_price"], 2),
            "exit_ts": exit_iso, "exit_price": round(exit_px, 2),
            "ret": ret, "pnl": round(pnl, 2), "reason": reason,
        })
        st["cash"] = proceeds
        st["units"] = 0.0
        st["position"] = 0
        st["open_trade"] = None

    # 1) stop-loss (only while in position, if enabled) — against lows since entry
    if st["position"] == 1 and st["open_trade"] and st["open_trade"].get("stop_price"):
        ot = st["open_trade"]
        after = df[df.index > pd.Timestamp(ot["entry_ts"])]
        hit = after[after["low"] <= ot["stop_price"]]
        if len(hit):
            close_trade(ot["stop_price"], str(hit.index[0]), "stop")
            st["armed"] = False  # require signal reset before re-entry

    # 2) reconcile with the signal: open/close at the current price
    if st["position"] == 1 and sig == 0:
        close_trade(cur_px, now_iso, "signal")
    elif st["position"] == 0 and sig == 1 and st["armed"]:
        entry_equity = st["cash"]
        units = entry_equity * (1 - FEE) / cur_px
        stop_price = None
        if cfg["stop"]:
            a = float(atr(df, cfg["atr_n"]).iloc[-1])
            stop_price = cur_px - cfg["k"] * a
        st["units"] = units
        st["cash"] = 0.0
        st["position"] = 1
        st["open_trade"] = {"entry_ts": now_iso, "entry_price": cur_px,
                            "entry_equity": entry_equity, "stop_price": stop_price}

    # re-arm: once flat and signal is 0 again, allow a fresh entry
    if st["position"] == 0 and sig == 0:
        st["armed"] = True
    st["last_signal"] = sig

    # 3) mark to market
    equity = st["cash"] + st["units"] * cur_px
    st["equity"].append({"t": now_iso, "e": round(equity, 2)})
    st["equity"] = st["equity"][-5000:]
    return equity


def build_output(state, cur_px, now_utc, dfd, dfh):
    out_strats = []
    for cfg in STRATS:
        st = state["strategies"][cfg["key"]]
        equity = st["cash"] + st["units"] * cur_px
        closed = st["trades"]
        wins = [t for t in closed if t["ret"] > 0]
        realized = sum(t["pnl"] for t in closed)
        open_trade = None
        unreal = 0.0
        if st["position"] == 1 and st["open_trade"]:
            ot = st["open_trade"]
            cur_val = st["units"] * cur_px
            unreal = cur_val - ot["entry_equity"]
            sp = ot.get("stop_price")
            open_trade = {
                "entry_ts": ot["entry_ts"], "entry_price": round(ot["entry_price"], 2),
                "current_price": round(cur_px, 2),
                "unreal_ret": cur_val / ot["entry_equity"] - 1.0,
                "unreal_pnl": round(unreal, 2),
                "stop_price": round(sp, 2) if sp else None,
                "stop_pct": (sp / ot["entry_price"] - 1.0) if sp else None,
            }
        out_strats.append({
            "key": cfg["key"], "base": cfg["base"], "tf": cfg["tf"],
            "has_stop": cfg["stop"], "color": cfg["color"],
            "stop_atr_n": cfg.get("atr_n"), "stop_k": cfg.get("k"),
            "summary": {
                "equity": round(equity, 2), "total_return": equity / CAPITAL - 1.0,
                "total_pnl": round(equity - CAPITAL, 2),
                "realized_pnl": round(realized, 2), "unrealized_pnl": round(unreal, 2),
                "closed_trades": len(closed), "open_trades": st["position"],
                "win_rate": (len(wins) / len(closed)) if closed else None,
                "position": st["position"], "armed": st["armed"], "signal": st["last_signal"],
            },
            "open_trade": open_trade,
            "trades": list(reversed(closed)),  # newest first
            "equity": st["equity"],
        })
    bh0 = state["bh_start_price"]
    bh_eq = CAPITAL * (1 - FEE) * cur_px / bh0
    bench = {"key": "bh", "color": "#64748b",
             "summary": {"equity": round(bh_eq, 2), "total_return": bh_eq / CAPITAL - 1.0,
                         "total_pnl": round(bh_eq - CAPITAL, 2), "position": 1},
             "entry_price": round(bh0, 2), "equity": state.get("bh_equity", [])}
    return {
        "schema": SCHEMA, "start_date": state["start_date"], "start_run": state["start_run"],
        "last_run_utc": now_utc.strftime("%Y-%m-%d %H:%M UTC"),
        "last_daily_close": str(dfd.index[-1].date()),
        "last_hourly_close": str(dfh.index[-1]),
        "fee": FEE, "start_capital": CAPITAL, "current_price": round(cur_px, 2),
        "donchian_n": DONCHIAN_N, "data_source": SOURCE["name"],
        "strategies": out_strats, "benchmark": bench,
    }


def sane(o):
    if isinstance(o, float):
        return o if (o == o and abs(o) != float("inf")) else None
    if isinstance(o, dict):
        return {k: sane(v) for k, v in o.items()}
    if isinstance(o, list):
        return [sane(v) for v in o]
    return o


def main():
    dfd = klines("1d", 300)
    dfh = klines("1h", 600)
    cur_px = ticker_price()
    now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    state = {}
    if os.path.exists(STATE):
        try:
            state = json.load(open(STATE, encoding="utf-8"))
        except Exception:
            state = {}
    if state.get("schema") != SCHEMA:  # fresh start from today
        state = {
            "schema": SCHEMA,
            "start_date": now_utc.strftime("%Y-%m-%d"),
            "start_run": now_utc.strftime("%Y-%m-%d %H:%M UTC"),
            "bh_start_price": cur_px,
            "bh_equity": [],
            "strategies": {c["key"]: new_strat_state() for c in STRATS},
        }
        print(f"[FRESH START] {state['start_date']} benchmark entry ${cur_px:.0f}")
    state.setdefault("bh_equity", [])

    for cfg in STRATS:
        step(state["strategies"][cfg["key"]], cfg, dfd, dfh, cur_px, now_utc)

    now_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%S")
    bh_eq = CAPITAL * (1 - FEE) * cur_px / state["bh_start_price"]
    state["bh_equity"].append({"t": now_iso, "e": round(bh_eq, 2)})
    state["bh_equity"] = state["bh_equity"][-5000:]

    out = build_output(state, cur_px, now_utc, dfd, dfh)

    json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write("window.PAPER = ")
        json.dump(sane(out), f, ensure_ascii=False)
        f.write(";\n")

    print(f"[{out['last_run_utc']}] BTC ${cur_px:.0f}  start {out['start_date']}  source {SOURCE['name']}")
    for s in out["strategies"]:
        sm = s["summary"]
        pos = "LONG" if sm["position"] else "cash"
        stop = "+stop" if s["has_stop"] else "     "
        print(f"  {s['base']:<9}{stop}  profit {sm['total_pnl']:+8.0f}$ ({sm['total_return']*100:+5.1f}%)  "
              f"{pos:<4}  closed:{sm['closed_trades']}")
    bm = out["benchmark"]["summary"]
    print(f"  {'buy&hold':<14}  profit {bm['total_pnl']:+8.0f}$ ({bm['total_return']*100:+5.1f}%)")


if __name__ == "__main__":
    main()
