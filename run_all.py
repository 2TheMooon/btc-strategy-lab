"""
Главный прогон: загружает данные, гоняет все стратегии в двух режимах
(ПОДГОНКА и WALK-FORWARD) на дневных и часовых данных, пишет results.json.
"""
import os
import json
import math
import numpy as np
import pandas as pd
from engine import STRATEGIES, buy_hold
from optimize import build_grid, in_sample_best, walk_forward, optimization_surface

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
FEE = 0.001  # 0.1% за сделку (вход/выход) — реалистично для спота с проскальзыванием

PPY = {"daily": 365, "hourly": 24 * 365}


def load(interval):
    df = pd.read_csv(os.path.join(DATA, f"btc_{interval}.csv"))
    df["dt"] = pd.to_datetime(df["time"], unit="ms")
    df = df.set_index("dt").sort_index()
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    return df


# ---- Сетки параметров -------------------------------------------------------
GRIDS_DAILY = {
    "sma_cross": {"fast": [5, 10, 15, 20, 30, 40, 50], "slow": [50, 75, 100, 125, 150, 200]},
    "ema_cross": {"fast": [5, 8, 10, 12, 15, 20, 25], "slow": [26, 40, 50, 75, 100, 150]},
    "macd": {"fast": [8, 10, 12], "slow": [21, 26, 30], "signal": [7, 9, 12]},
    "rsi_meanrev": {"n": [7, 10, 14, 21], "low": [20, 25, 30, 35], "high": [60, 65, 70, 75]},
    "boll_breakout": {"n": [10, 20, 30, 40], "k": [1.5, 2.0, 2.5, 3.0]},
    "boll_meanrev": {"n": [10, 20, 30, 40], "k": [1.5, 2.0, 2.5, 3.0]},
    "donchian": {"n": [10, 15, 20, 25, 30, 40, 55]},
    "momentum": {"n": [10, 20, 30, 45, 60, 90], "thresh": [0.0, 0.02, 0.05, 0.10]},
    "trend_rsi": {"trend": [50, 100, 150, 200], "n": [7, 14], "low": [25, 30, 35], "high": [55, 60, 70]},
}

GRIDS_HOURLY = {
    "ema_cross": {"fast": [5, 9, 12, 21, 30], "slow": [21, 40, 60, 100, 150]},
    "sma_cross": {"fast": [10, 20, 30, 50], "slow": [60, 100, 150, 200]},
    "rsi_meanrev": {"n": [7, 14, 21], "low": [15, 20, 25, 30], "high": [65, 70, 75, 80]},
    "boll_breakout": {"n": [20, 40, 60, 80], "k": [1.5, 2.0, 2.5, 3.0]},
    "boll_meanrev": {"n": [20, 40, 60], "k": [1.5, 2.0, 2.5]},
    "donchian": {"n": [12, 24, 48, 72, 96]},
    "macd": {"fast": [8, 12], "slow": [21, 26], "signal": [9, 12]},
    "momentum": {"n": [12, 24, 48, 72], "thresh": [0.0, 0.01, 0.02]},
}

WF = {
    "daily": dict(train_init=730, test_step=182),
    "hourly": dict(train_init=24 * 365, test_step=24 * 60),
}


def ser_to_obj(eq, daily_idx, ndigits=5):
    """Сериализация эквити; часовую ресемплим до дневной для лёгкого графика."""
    if not daily_idx:
        eq = eq.resample("1D").last().dropna()
    return {
        "dates": [str(d.date()) for d in eq.index],
        "values": [round(float(v), ndigits) for v in eq.values],
    }


def sanitize(o):
    if isinstance(o, dict):
        return {k: sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [sanitize(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        o = float(o)
    if isinstance(o, float):
        if math.isnan(o) or math.isinf(o):
            return None
        return o
    return o


def run_timeframe(tf, df, grids):
    ppy = PPY[tf]
    daily_idx = tf == "daily"
    out = []
    for key, spec in grids.items():
        grid = build_grid(spec)
        ins = in_sample_best(df, key, grid, FEE, ppy)
        wf = walk_forward(df, key, grid, FEE, ppy, **WF[tf])
        # buy & hold на том же OOS-окне для честного сравнения
        oos_lo = wf["oos_start"]
        bh_net, bh_m = buy_hold(df["close"].iloc[oos_lo:], FEE, ppy)
        meta = STRATEGIES[key]
        out.append({
            "key": key,
            "name": meta["name"],
            "formula": meta["formula"],
            "n_combos": len(grid),
            "insample": {
                "params": ins["params"],
                "metrics": ins["metrics"],
                "equity": ser_to_obj(ins["equity"], daily_idx),
            },
            "walkforward": {
                "metrics": wf["metrics"],
                "equity": ser_to_obj(wf["equity"], daily_idx),
                "folds": wf["folds"],
                "oos_start_date": wf["oos_start_date"],
                "bh_oos_return": bh_m["total_return"],
                "bh_oos_sharpe": bh_m["sharpe"],
            },
        })
        print(f"  [{tf}] {key}: подгонка Sharpe={ins['metrics']['sharpe']:.2f} "
              f"ret={ins['metrics']['total_return']*100:.0f}% | "
              f"walk-forward Sharpe={wf['metrics']['sharpe']:.2f} "
              f"ret={wf['metrics']['total_return']*100:.0f}% "
              f"(B&H {bh_m['total_return']*100:.0f}%)")
    return out


def main():
    print("Загружаю данные...")
    d = load("1d")
    h = load("1h")
    print(f"  дневных={len(d)}  часовых={len(h)}")
    print(f"  период: {d.index[0].date()} .. {d.index[-1].date()}")

    # buy & hold по всей истории (дневной)
    bh_net, bh_m = buy_hold(d["close"], FEE, PPY["daily"])
    from engine import equity_from_net
    bh_eq = equity_from_net(bh_net)

    print("Дневные стратегии (среднесрок / ~раз в неделю):")
    daily = run_timeframe("daily", d, GRIDS_DAILY)
    print("Часовые стратегии (дейтрейдинг):")
    hourly = run_timeframe("hourly", h, GRIDS_HOURLY)

    # выбор лучших по walk-forward (вне выборки) Sharpe
    def best_by_oos(lst):
        return max(lst, key=lambda s: (s["walkforward"]["metrics"]["sharpe"] or -9))["key"]

    def best_by_insample(lst):
        return max(lst, key=lambda s: (s["insample"]["metrics"]["sharpe"] or -9))["key"]

    best_weekly = best_by_oos(daily)
    best_daytrade = best_by_oos(hourly)

    # карта подгонки для SMA-кросса (дневной) — наглядность оверфиттинга
    surf = optimization_surface(d, "sma_cross", build_grid(GRIDS_DAILY["sma_cross"]), FEE, PPY["daily"])

    result = {
        "meta": {
            "symbol": "BTC/USDT",
            "source": "Binance",
            "fee_per_trade": FEE,
            "years": 5,
            "date_start": str(d.index[0].date()),
            "date_end": str(d.index[-1].date()),
            "n_daily": len(d),
            "n_hourly": len(h),
            "wf_daily": WF["daily"],
            "wf_hourly": WF["hourly"],
        },
        "price": {
            "dates": [str(x.date()) for x in d.index],
            "close": [round(float(v), 1) for v in d["close"].values],
        },
        "buyhold": {"metrics": bh_m, "equity": ser_to_obj(bh_eq, True)},
        "daily_strategies": daily,
        "hourly_strategies": hourly,
        "best_weekly": best_weekly,
        "best_weekly_insample": best_by_insample(daily),
        "best_daytrade": best_daytrade,
        "best_daytrade_insample": best_by_insample(hourly),
        "sma_surface": surf,
    }

    path = os.path.join(HERE, "results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sanitize(result), f, ensure_ascii=False)
    print(f"\nЗаписано: {path}  ({os.path.getsize(path)//1024} КБ)")
    print(f"Лучшая недельная (вне выборки): {best_weekly}")
    print(f"Лучшая дейтрейдинг (вне выборки): {best_daytrade}")


if __name__ == "__main__":
    main()
