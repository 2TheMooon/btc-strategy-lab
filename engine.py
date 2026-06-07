"""
Движок бэктеста БЕЗ заглядывания в будущее (no lookahead).

Конвенция исполнения (стандартная векторная):
  - На закрытии бара t стратегия решает целевую позицию tpos[t]
    (индикаторы используют только данные <= t).
  - В течение бара t+1 удерживается tpos[t]; доход = tpos[t] * r[t+1].
  - Комиссия списывается в момент изменения позиции:
        cost[t] = |tpos[t] - tpos[t-1]| * fee
  Это исключает заглядывание в будущее: решение в t -> доход в t+1.

Позиции long/flat: tpos в {0, 1}. (Спот, без шортов — реалистично для розницы.)
"""
import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------
# Индикаторы
# ----------------------------------------------------------------------------
def sma(s, n):
    return s.rolling(n).mean()


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(s, n=14):
    delta = s.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    # сглаживание Уайлдера
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
    """Удержание позиции: вход по entry, держим пока не сработает exit_.
    entry/exit_ — булевы Series; условия взаимоисключающие в наших стратегиях."""
    raw = pd.Series(np.nan, index=entry.index)
    raw[entry.values] = 1.0
    raw[exit_.values] = 0.0
    return raw.ffill().fillna(0.0)


# ----------------------------------------------------------------------------
# Стратегии: f(df, **params) -> целевая позиция tpos в {0,1}
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
    hi = df["high"].rolling(n).max().shift(1)   # канал ПРЕДЫДУЩИХ n баров
    lo = df["low"].rolling(n).min().shift(1)
    return _hold(c > hi, c < lo)


def st_momentum(df, n, thresh):
    return (roc(df["close"], n) > thresh).astype(float)


def st_sma_trend_rsi(df, trend, n, low, high):
    """Покупка на откате (RSI<low), но только при бычьем тренде (close>SMA(trend))."""
    c = df["close"]
    up = c > sma(c, trend)
    r = rsi(c, n)
    entry = (r < low) & up
    exit_ = (r > high) | (~up)
    return _hold(entry, exit_)


# Реестр стратегий: ключ -> (функция, имя параметров, сетка, формула, описание)
STRATEGIES = {
    "sma_cross": {
        "fn": st_sma_cross,
        "pnames": ["fast", "slow"],
        "name": "Пересечение скользящих средних (SMA)",
        "formula": "Long если SMA(fast) > SMA(slow), иначе вне рынка",
    },
    "ema_cross": {
        "fn": st_ema_cross,
        "pnames": ["fast", "slow"],
        "name": "Пересечение экспоненциальных средних (EMA)",
        "formula": "Long если EMA(fast) > EMA(slow), иначе вне рынка",
    },
    "macd": {
        "fn": st_macd,
        "pnames": ["fast", "slow", "signal"],
        "name": "MACD (схождение/расхождение средних)",
        "formula": "Long если линия MACD > сигнальной линии",
    },
    "rsi_meanrev": {
        "fn": st_rsi_meanrev,
        "pnames": ["n", "low", "high"],
        "name": "RSI возврат к среднему",
        "formula": "Покупка при RSI<low (перепроданность), выход при RSI>high",
    },
    "boll_breakout": {
        "fn": st_boll_breakout,
        "pnames": ["n", "k"],
        "name": "Пробой полос Боллинджера",
        "formula": "Покупка при close>верхней полосы, выход при возврате к средней",
    },
    "boll_meanrev": {
        "fn": st_boll_meanrev,
        "pnames": ["n", "k"],
        "name": "Возврат к среднему (Боллинджер)",
        "formula": "Покупка при close<нижней полосы, выход при возврате к средней",
    },
    "donchian": {
        "fn": st_donchian,
        "pnames": ["n"],
        "name": "Пробой канала Дончиана (черепахи)",
        "formula": "Покупка при пробое максимума n баров, выход при пробое минимума",
    },
    "momentum": {
        "fn": st_momentum,
        "pnames": ["n", "thresh"],
        "name": "Моментум (импульс цены)",
        "formula": "Long если доходность за n баров > порога",
    },
    "trend_rsi": {
        "fn": st_sma_trend_rsi,
        "pnames": ["trend", "n", "low", "high"],
        "name": "Откат по тренду (SMA-фильтр + RSI)",
        "formula": "Покупка на откате RSI<low ТОЛЬКО при close>SMA(trend)",
    },
}


# ----------------------------------------------------------------------------
# Ядро бэктеста
# ----------------------------------------------------------------------------
def backtest(close, tpos, fee):
    """Возвращает net-доходности (Series) для целевой позиции tpos."""
    r = close.pct_change().fillna(0.0)
    held = tpos.shift(1).fillna(0.0)          # позиция, удерживаемая в течение бара t
    gross = held * r
    turn = (tpos - tpos.shift(1)).abs()
    turn.iloc[0] = abs(tpos.iloc[0])
    cost = turn * fee
    net = gross - cost
    return net


def equity_from_net(net):
    return (1.0 + net).cumprod()


def extract_trades(close, tpos, fee):
    """Список доходностей сделок (round-trip), согласован с net-конвенцией:
    вход по close в баре решения 0->1, выход по close в баре решения 1->0."""
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
            netr = gross - 2.0 * fee  # комиссия вход+выход (аддитивно, как в backtest)
            trades.append(netr)
            in_pos = False
    if in_pos:  # закрываем в конце по последней цене
        gross = c[-1] / entry_px - 1.0
        netr = gross - 2.0 * fee
        trades.append(netr)
    return trades


def metrics(net, tpos, close, fee, ppy):
    """Сводные метрики стратегии."""
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
