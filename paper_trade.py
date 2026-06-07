"""
ЖИВАЯ бумажная торговля (симуляция, НЕ реальные ордера) — старт с сегодняшнего дня.

Три стратегии торгуют BTC параллельно, капитал $10 000 на каждую:
  1) ПОДГОНКА   — Моментум 30/0.10            (дневные, без стопа)
  2) ВСЛЕПУЮ    — MACD 12/26/9                (дневные, без стопа)
  3) ДЕЙТРЕЙД   — Пробой канала Дончиана 48ч  (часовые, стоп-лосс 2.5×ATR(24))
Плюс эталон Buy & Hold (с момента старта).

Состояние ведётся пошагово (paper_state.json): позиция, открытая сделка, журнал
закрытых сделок, кривая капитала. На каждом запуске рутина:
  - тянет свежие закрытые свечи и текущую цену;
  - проверяет стоп-лосс (по минимумам часовых баров с момента входа);
  - сверяет позицию с текущим сигналом, открывает/закрывает сделки по текущей цене;
  - пишет открытые сделки и общий профит в site/paper.js (раздел сайта).
Идемпотентно по времени: входы/выходы происходят при изменении сигнала/стопа.

ВАЖНО: реальные ордера на бирже не выставляются. Это симуляция.
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
SCHEMA = 3

FEE = 0.001
CAPITAL = 10000.0
DONCHIAN_N = 48
ATR_N = 24
ATR_K = 2.5

STRATS = [
    {"key": "fit", "label": "Подгонка · Моментум 30/0.10", "kind": "подгонка",
     "tf": "daily", "params": "n=30, порог=10%", "color": "#f59e0b", "stop": False,
     "fn": lambda df: st_momentum(df, 30, 0.10),
     "stop_desc": "без стопа (выход по сигналу)"},
    {"key": "blind", "label": "Вслепую · MACD 12/26/9", "kind": "вслепую",
     "tf": "daily", "params": "12 / 26 / 9", "color": "#2dd4bf", "stop": False,
     "fn": lambda df: st_macd(df, 12, 26, 9),
     "stop_desc": "без стопа (выход по сигналу)"},
    {"key": "donchian_h", "label": "Дейтрейд · Дончиан 48ч + стоп", "kind": "дейтрейдинг",
     "tf": "hourly", "params": "канал 48ч", "color": "#a78bfa", "stop": True,
     "fn": lambda df: st_donchian(df, DONCHIAN_N),
     "stop_desc": f"стоп-лосс {ATR_K}×ATR({ATR_N})"},
]


# Источники данных с резервом: Binance часто блокирует IP облака (США),
# поэтому пробуем зеркало data-vision, затем основной Binance, затем Kraken.
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
    raw = [k for k in raw if int(k[6]) < now]  # только закрытые свечи
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
    """Один шаг живой симуляции для одной стратегии."""
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

    # 1) стоп-лосс (только пока в позиции и стоп задан) — по минимумам баров с входа
    if st["position"] == 1 and st["open_trade"] and st["open_trade"].get("stop_price"):
        ot = st["open_trade"]
        entry_t = pd.Timestamp(ot["entry_ts"])
        after = dfh[dfh.index > entry_t]
        hit = after[after["low"] <= ot["stop_price"]]
        if len(hit):
            close_trade(ot["stop_price"], str(hit.index[0]), "стоп")
            st["armed"] = False  # после стопа ждём сброса сигнала

    # 2) сверка с сигналом: вход/выход по ТЕКУЩЕЙ цене
    if st["position"] == 1 and sig == 0:
        close_trade(cur_px, now_iso, "сигнал")
    elif st["position"] == 0 and sig == 1 and st["armed"]:
        entry_equity = st["cash"]
        units = entry_equity * (1 - FEE) / cur_px
        stop_price = None
        if cfg["stop"]:
            a = float(atr(dfh, ATR_N).iloc[-1])
            stop_price = cur_px - ATR_K * a
        st["units"] = units
        st["cash"] = 0.0
        st["position"] = 1
        st["open_trade"] = {"entry_ts": now_iso, "entry_price": cur_px,
                            "entry_equity": entry_equity, "stop_price": stop_price}

    # перевзвод стопа: после выхода ждём, пока сигнал снова станет 0, затем разрешаем вход
    if st["position"] == 0 and sig == 0:
        st["armed"] = True
    st["last_signal"] = sig

    # 3) отметка капитала
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
            "key": cfg["key"], "label": cfg["label"], "kind": cfg["kind"],
            "tf": "часовые" if cfg["tf"] == "hourly" else "дневные",
            "params": cfg["params"], "color": cfg["color"], "stop_desc": cfg["stop_desc"],
            "summary": {
                "equity": round(equity, 2), "total_return": equity / CAPITAL - 1.0,
                "total_pnl": round(equity - CAPITAL, 2),
                "realized_pnl": round(realized, 2), "unrealized_pnl": round(unreal, 2),
                "closed_trades": len(closed), "open_trades": st["position"],
                "win_rate": (len(wins) / len(closed)) if closed else None,
                "position": st["position"], "armed": st["armed"], "signal": st["last_signal"],
            },
            "open_trade": open_trade,
            "trades": list(reversed(closed)),  # новые сверху
            "equity": st["equity"],
        })
    # эталон buy & hold с момента старта
    bh0 = state["bh_start_price"]
    bh_eq = CAPITAL * (1 - FEE) * cur_px / bh0
    bench = {"label": "BTC «купи и держи»", "color": "#64748b",
             "summary": {"equity": round(bh_eq, 2), "total_return": bh_eq / CAPITAL - 1.0,
                         "total_pnl": round(bh_eq - CAPITAL, 2), "position": 1},
             "entry_price": round(bh0, 2), "equity": state.get("bh_equity", [])}
    return {
        "schema": SCHEMA, "start_date": state["start_date"], "start_run": state["start_run"],
        "last_run": now_utc.astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        "last_run_utc": now_utc.strftime("%Y-%m-%d %H:%M UTC"),
        "last_daily_close": str(dfd.index[-1].date()),
        "last_hourly_close": str(dfh.index[-1]),
        "fee": FEE, "start_capital": CAPITAL, "current_price": round(cur_px, 2),
        "donchian_n": DONCHIAN_N, "atr_k": ATR_K, "atr_n": ATR_N,
        "data_source": SOURCE["name"],
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
    if state.get("schema") != SCHEMA:  # старт заново с сегодняшнего дня
        state = {
            "schema": SCHEMA,
            "start_date": now_utc.strftime("%Y-%m-%d"),
            "start_run": now_utc.astimezone().strftime("%Y-%m-%d %H:%M %Z"),
            "bh_start_price": cur_px,
            "bh_equity": [],
            "strategies": {c["key"]: new_strat_state() for c in STRATS},
        }
        print(f"[НОВЫЙ СТАРТ] {state['start_date']} цена входа эталона ${cur_px:.0f}")
    state.setdefault("bh_equity", [])

    for cfg in STRATS:
        step(state["strategies"][cfg["key"]], cfg, dfd, dfh, cur_px, now_utc)

    # кривая капитала эталона buy & hold
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

    print(f"[{out['last_run']}] BTC ${cur_px:.0f}  старт {out['start_date']}")
    for s in out["strategies"]:
        sm = s["summary"]
        pos = "В РЫНКЕ" if sm["position"] else "в кэше"
        ot = ""
        if s["open_trade"]:
            ot = f" | откр.сделка вход ${s['open_trade']['entry_price']:.0f} ({s['open_trade']['unreal_ret']*100:+.1f}%)"
            if s["open_trade"]["stop_price"]:
                ot += f" стоп ${s['open_trade']['stop_price']:.0f}"
        print(f"  {s['label']:<34} профит {sm['total_pnl']:+.0f}$ ({sm['total_return']*100:+.1f}%)  "
              f"{pos}  сделок:{sm['closed_trades']}{ot}")
    bm = out["benchmark"]["summary"]
    print(f"  {'BTC купи и держи':<34} профит {bm['total_pnl']:+.0f}$ ({bm['total_return']*100:+.1f}%)")


if __name__ == "__main__":
    main()
