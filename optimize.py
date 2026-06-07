"""
Подгонка (in-sample grid search) и walk-forward (вне выборки).

Идея двух взглядов:
  1) ПОДГОНКА  — параметры выбираются по ВСЕЙ истории и на ней же оцениваются.
     Это "подгонка под график": мы как будто видим будущее. Красиво, но обман.
  2) WALK-FORWARD — на каждом шаге параметры выбираются ТОЛЬКО по прошлым данным
     (train), затем торгуются на следующем, ещё НЕ виденном окне (test).
     Тесты склеиваются в одну честную "вслепую" эквити. Это реальный результат.
"""
import itertools
import numpy as np
import pandas as pd
from engine import STRATEGIES, backtest, metrics, equity_from_net


def build_grid(spec):
    """spec: dict param->list. Возвращает список dict-комбинаций с фильтрами."""
    keys = list(spec.keys())
    out = []
    for vals in itertools.product(*[spec[k] for k in keys]):
        d = dict(zip(keys, vals))
        if "fast" in d and "slow" in d and d["fast"] >= d["slow"]:
            continue
        if "low" in d and "high" in d and d["low"] >= d["high"]:
            continue
        out.append(d)
    return out


def precompute_nets(df, key, grid, fee):
    """Для каждой комбинации параметров считаем tpos и net по ВСЕЙ истории один раз."""
    fn = STRATEGIES[key]["fn"]
    close = df["close"]
    res = []
    for params in grid:
        tpos = fn(df, **params)
        tpos = tpos.reindex(df.index).fillna(0.0).clip(0, 1)
        net = backtest(close, tpos, fee)
        res.append((params, tpos, net))
    return res


def _score(net_slice, min_pts=30):
    """Целевая функция отбора параметров: годовой Sharpe (на срезе train)."""
    if len(net_slice) < min_pts or net_slice.std() == 0:
        return -1e9
    return net_slice.mean() / net_slice.std()


def in_sample_best(df, key, grid, fee, ppy):
    """ПОДГОНКА: лучшая комбинация по всей истории + её метрики на всей истории."""
    close = df["close"]
    pre = precompute_nets(df, key, grid, fee)
    best = None
    for params, tpos, net in pre:
        sc = _score(net)
        if best is None or sc > best[0]:
            best = (sc, params, tpos, net)
    _, params, tpos, net = best
    m = metrics(net, tpos, close, fee, ppy)
    eq = equity_from_net(net)
    return {"params": params, "metrics": m, "equity": eq, "net": net, "tpos": tpos}


def walk_forward(df, key, grid, fee, ppy, train_init, test_step):
    """WALK-FORWARD (вне выборки): расширяющийся train, фиксированный шаг test.
    На каждом шаге выбираем параметры по train, торгуем их на test."""
    close = df["close"]
    n = len(df)
    pre = precompute_nets(df, key, grid, fee)  # считаем один раз, переиспользуем
    tpos_oos = pd.Series(0.0, index=df.index)
    folds = []
    start = train_init
    while start < n:
        end = start + test_step
        if n - end < test_step:      # маленький хвост присоединяем к последнему окну
            end = n
        end = min(end, n)
        # отбор параметров по train = [0:start]
        best = None
        for params, tpos, net in pre:
            sc = _score(net.iloc[:start])
            if best is None or sc > best[0]:
                best = (sc, params, tpos, net)
        score, params, btpos, bnet = best
        # ожидаемый (на обучении) Sharpe выбранных параметров, годовой
        train_sharpe = float(score * np.sqrt(ppy)) if score > -1e8 else None
        # фиксируем позиции этого фолда на окне test
        tpos_oos.iloc[start:end] = btpos.iloc[start:end].values
        # метрики только на test-окне
        tm = metrics(bnet.iloc[start:end], btpos.iloc[start:end],
                     close.iloc[start:end], fee, ppy)
        folds.append({
            "start": int(start), "end": int(end),
            "start_date": str(df.index[start].date()),
            "end_date": str(df.index[end - 1].date()),
            "params": params,
            "train_sharpe": train_sharpe,
            "test_return": tm["total_return"],
            "test_sharpe": tm["sharpe"],
        })
        start = end
    # склеенная честная эквити по фактическим позициям walk-forward
    oos_lo = train_init
    net_oos = backtest(close.iloc[oos_lo:], tpos_oos.iloc[oos_lo:], fee)
    m = metrics(net_oos, tpos_oos.iloc[oos_lo:], close.iloc[oos_lo:], fee, ppy)
    eq = equity_from_net(net_oos)
    tr = [f["train_sharpe"] for f in folds if f["train_sharpe"] is not None]
    te = [f["test_sharpe"] for f in folds]
    return {
        "metrics": m, "equity": eq, "net": net_oos,
        "tpos": tpos_oos.iloc[oos_lo:], "folds": folds,
        "avg_train_sharpe": float(np.mean(tr)) if tr else None,
        "avg_test_sharpe": float(np.mean(te)) if te else None,
        "oos_start": int(oos_lo), "oos_start_date": str(df.index[oos_lo].date()),
    }


def optimization_surface(df, key, grid, fee, ppy):
    """Карта результатов по всей истории — для визуализации подгонки (2 параметра)."""
    fn = STRATEGIES[key]["fn"]
    close = df["close"]
    rows = []
    for params in grid:
        tpos = fn(df, **params).reindex(df.index).fillna(0.0).clip(0, 1)
        net = backtest(close, tpos, fee)
        eq = equity_from_net(net)
        sh = float(net.mean() / net.std() * np.sqrt(ppy)) if net.std() > 0 else 0.0
        rows.append({**params, "sharpe": sh, "total_return": float(eq.iloc[-1] - 1)})
    return rows
