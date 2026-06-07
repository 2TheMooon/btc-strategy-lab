"""
No-lookahead backtest engine.

Execution convention (standard vectorized):
  - At the close of bar t the strategy decides the target position tpos[t]
    (indicators use only data <= t).
  - During bar t+1 we hold tpos[t]; return = tpos[t] * r[t+1].
  - The fee is charged at the moment the position changes:
        cost[t] = |tpos[t] - tpos[t-1]| * fee
  This rules out lookahead: a decision at t -> a return at t+1.

Long/flat positions: tpos in {0, 1}. (Spot, no shorts — realistic for retail.)
"""
import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------
# Indicators
# ----------------------------------------------------------------------------
def sma(s, n):
    return s.rolling(n).mean()


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(s, n=14):
    delta = s.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    # Wilder smoothing
    roll_up = up.ewm(alpha=1 / n, adjust=False).mean()
    roll_down = down.ewm(alpha=1 / n, adjust=False).mean()
    rs = roll_up / roll_down.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.fillna(50)


def macd(s, fast=12, slow=26, signal=9):
    line = ema(s, fast) - ema(s, slow)
    sig = line.ewm(span=signal, adjust=False).mean()
    return line, sig


def bollinger(s, n=20, k=2.0):
    mid = sma(s, n)
    sd = s.rolling(n).std()
    return mid - k * sd, mid, mid + k * sd


def roc(s, n):
    return s.pct_change(n)


def atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def _hold(entry, exit_):
    """Hold a position: enter on `entry`, hold until `exit_` fires.
    entry/exit_ are boolean Series; the conditions are mutually exclusive in our strategies."""
    raw = pd.Series(np.nan, index=entry.index)
    raw[entry.values] = 1.0
    raw[exit_.values] = 0.0
    return raw.ffill().fillna(0.0)


# ----------------------------------------------------------------------------
# Strategies: f(df, **params) -> target position tpos in {0,1}
# ----------------------------------------------------------------------------
def st_sma_cross(df, fast, slow):
    c = df["close"]
    return (sma(c, fast) > sma(c, slow)).astype(float)


def st_ema_cross(df, fast, slow):
    c = df["close"]
    return (ema(c, fast) > ema(c, slow)).astype(float)


def st_macd(df, fast, slow, signal):
    line, sig = macd(df["close"], fast, slow, signal)
    return (line > sig).astype(float)


def st_rsi_meanrev(df, n, low, high):
    r = rsi(df["close"], n)
    return _hold(r < low, r > high)


def st_boll_breakout(df, n, k):
    c = df["close"]
    lower, mid, upper = bollinger(c, n, k)
    return _hold(c > upper, c < mid)


def st_boll_meanrev(df, n, k):
    c = df["close"]
    lower, mid, upper = bollinger(c, n, k)
    return _hold(c < lower, c > mid)


def st_donchian(df, n):
    c = df["close"]
    hi = df["high"].rolling(n).max().shift(1)   # channel of the PREVIOUS n bars
    lo = df["low"].rolling(n).min().shift(1)
    return _hold(c > hi, c < lo)


def st_momentum(df, n, thresh):
    return (roc(df["close"], n) > thresh).astype(float)


def st_sma_trend_rsi(df, trend, n, low, high):
    """Buy the dip (RSI<low), but only in a bullish trend (close>SMA(trend))."""
    c = df["close"]
    up = c > sma(c, trend)
    r = rsi(c, n)
    entry = (r < low) & up
    exit_ = (r > high) | (~up)
    return _hold(entry, exit_)


# Strategy registry: key -> (function, param names, grid, formula, description).
# Display names live in the site i18n (site/i18n.js); these are fallbacks / for results.json.
STRATEGIES = {
    "sma_cross": {
        "fn": st_sma_cross,
        "pnames": ["fast", "slow"],
        "name": "Moving-average cross (SMA)",
        "formula": "Long if SMA(fast) > SMA(slow), else flat",
    },
    "ema_cross": {
        "fn": st_ema_cross,
        "pnames": ["fast", "slow"],
        "name": "Exponential-MA cross (EMA)",
        "formula": "Long if EMA(fast) > EMA(slow), else flat",
    },
    "macd": {
        "fn": st_macd,
        "pnames": ["fast", "slow", "signal"],
        "name": "MACD (moving-average convergence/divergence)",
        "formula": "Long if the MACD line > the signal line",
    },
    "rsi_meanrev": {
        "fn": st_rsi_meanrev,
        "pnames": ["n", "low", "high"],
        "name": "RSI mean-reversion",
        "formula": "Buy when RSI<low (oversold), exit when RSI>high",
    },
    "boll_breakout": {
        "fn": st_boll_breakout,
        "pnames": ["n", "k"],
        "name": "Bollinger Band breakout",
        "formula": "Buy when close>upper band, exit on return to the middle",
    },
    "boll_meanrev": {
        "fn": st_boll_meanrev,
        "pnames": ["n", "k"],
        "name": "Mean-reversion (Bollinger)",
        "formula": "Buy when close<lower band, exit on return to the middle",
    },
    "donchian": {
        "fn": st_donchian,
        "pnames": ["n"],
        "name": "Donchian channel breakout (turtles)",
        "formula": "Buy on break of the n-bar high, exit on break of the n-bar low",
    },
    "momentum": {
        "fn": st_momentum,
        "pnames": ["n", "thresh"],
        "name": "Momentum",
        "formula": "Long if the return over n bars > threshold",
    },
    "trend_rsi": {
        "fn": st_sma_trend_rsi,
        "pnames": ["trend", "n", "low", "high"],
        "name": "Pullback in a trend (SMA filter + RSI)",
        "formula": "Buy the dip RSI<low ONLY when close>SMA(trend)",
    },
}


# ----------------------------------------------------------------------------
# Backtest core
# ----------------------------------------------------------------------------
def backtest(close, tpos, fee):
    """Return net returns (Series) for the target position tpos."""
    r = close.pct_change().fillna(0.0)
    held = tpos.shift(1).fillna(0.0)          # position held during bar t
    gross = held * r
    turn = (tpos - tpos.shift(1)).abs()
    turn.iloc[0] = abs(tpos.iloc[0])
    cost = turn * fee
    net = gross - cost
    return net


def equity_from_net(net):
    return (1.0 + net).cumprod()


def extract_trades(close, tpos, fee):
    """List of round-trip trade returns, consistent with the net convention:
    enter at the close of the 0->1 decision bar, exit at the close of the 1->0 decision bar."""
    pos = tpos.values
    c = close.values
    trades = []
    in_pos = False
    entry_px = None
    for i in range(len(pos)):
        if not in_pos and pos[i] == 1:
            in_pos = True
            entry_px = c[i]
        elif in_pos and pos[i] == 0:
            exit_px = c[i]
            gross = exit_px / entry_px - 1.0
            netr = gross - 2.0 * fee  # entry+exit fee (additive, as in backtest)
            trades.append(netr)
            in_pos = False
    if in_pos:  # close at the end at the last price
        gross = c[-1] / entry_px - 1.0
        netr = gross - 2.0 * fee
        trades.append(netr)
    return trades


def metrics(net, tpos, close, fee, ppy):
    """Summary metrics for a strategy."""
    eq = equity_from_net(net)
    total = float(eq.iloc[-1] - 1.0)
    n = len(net)
    years = n / ppy
    cagr = float(eq.iloc[-1] ** (1.0 / years) - 1.0) if years > 0 and eq.iloc[-1] > 0 else -1.0
    vol = float(net.std() * np.sqrt(ppy))
    mean_ann = float(net.mean() * ppy)
    sharpe = float(net.mean() / net.std() * np.sqrt(ppy)) if net.std() > 0 else 0.0
    downside = net[net < 0]
    sortino = float(net.mean() / downside.std() * np.sqrt(ppy)) if len(downside) > 1 and downside.std() > 0 else 0.0
    run_max = eq.cummax()
    dd = eq / run_max - 1.0
    maxdd = float(dd.min())
    calmar = float(cagr / abs(maxdd)) if maxdd < 0 else 0.0
    exposure = float((tpos != 0).mean())
    trades = extract_trades(close, tpos, fee)
    ntr = len(trades)
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    win_rate = float(len(wins) / ntr) if ntr else 0.0
    avg_trade = float(np.mean(trades)) if ntr else 0.0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = float(gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)
    return {
        "total_return": total,
        "cagr": cagr,
        "ann_return": mean_ann,
        "ann_vol": vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": maxdd,
        "calmar": calmar,
        "exposure": exposure,
        "num_trades": ntr,
        "win_rate": win_rate,
        "avg_trade": avg_trade,
        "profit_factor": profit_factor if np.isfinite(profit_factor) else 99.0,
    }


def buy_hold(close, fee, ppy):
    tpos = pd.Series(1.0, index=close.index)
    net = backtest(close, tpos, fee)
    return net, metrics(net, tpos, close, fee, ppy)
