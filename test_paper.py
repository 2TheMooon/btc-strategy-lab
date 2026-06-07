"""Самотест логики живой торговли: вход, стоп-лосс, перевзвод, выход по сигналу."""
import datetime
import pandas as pd
import paper_trade as P

cur_sig = {"v": 0}
cfg = {"key": "t", "label": "T", "kind": "t", "tf": "hourly", "params": "",
       "color": "#fff", "stop": True, "stop_desc": "",
       "fn": lambda df: pd.Series([cur_sig["v"]] * len(df), index=df.index)}
st = P.new_strat_state()

base = [(101, 99, 100)] * 30  # high, low, close — диапазон 2 => ATR ~ 2 => стоп = 100-2.5*2 = 95


def dfh_from(extra):
    rows = base + extra
    idx = pd.date_range("2026-01-01", periods=len(rows), freq="h")
    return pd.DataFrame({"open": [r[2] for r in rows], "high": [r[0] for r in rows],
                         "low": [r[1] for r in rows], "close": [r[2] for r in rows]}, index=idx)


def run(dfh, px, sig, t):
    cur_sig["v"] = sig
    P.step(st, cfg, dfh, dfh, px, t)


t0 = datetime.datetime(2026, 1, 2, 0, 0)
ok = True


def check(name, cond):
    global ok
    ok = ok and cond
    print(("  OK  " if cond else " FAIL ") + name)


# 1) вход
run(dfh_from([(101, 99, 100)]), 100.0, 1, t0)
sp = st["open_trade"]["stop_price"] if st["open_trade"] else None
check(f"вход открыт, позиция=1, стоп≈95 (={round(sp,1) if sp else None})",
      st["position"] == 1 and sp is not None and abs(sp - 95) < 0.6)

# 2) стоп-лосс: бар с low=94 < 95
run(dfh_from([(101, 99, 100), (96, 94, 95)]), 95.0, 1, t0 + datetime.timedelta(hours=2))
check("стоп сработал: позиция=0, причина='стоп', armed=False",
      st["position"] == 0 and len(st["trades"]) == 1 and st["trades"][-1]["reason"] == "стоп" and not st["armed"])

# 3) сигнал=1, но armed=False -> повторного входа нет
run(dfh_from([(101, 99, 100), (96, 94, 95), (96, 94, 95)]), 95.0, 1, t0 + datetime.timedelta(hours=3))
check("после стопа повторного входа нет (armed-блок)", st["position"] == 0)

# 4) сигнал=0 -> перевзвод
run(dfh_from([(101, 99, 100), (96, 94, 95), (96, 94, 95)]), 95.0, 0, t0 + datetime.timedelta(hours=4))
check("перевзвод: armed=True", st["armed"] is True and st["position"] == 0)

# 5) сигнал=1 -> повторный вход
run(dfh_from([(101, 99, 100), (96, 94, 95), (96, 94, 95)]), 95.0, 1, t0 + datetime.timedelta(hours=5))
check("повторный вход: позиция=1", st["position"] == 1)

# 6) сигнал=0 на цене 105 -> выход по сигналу с прибылью (вход был 95)
run(dfh_from([(101, 99, 100), (96, 94, 95), (96, 94, 95), (106, 104, 105)]), 105.0, 0, t0 + datetime.timedelta(hours=6))
t = st["trades"][-1]
check(f"выход по сигналу с прибылью (ret={t['ret']*100:.1f}%)",
      st["position"] == 0 and t["reason"] == "сигнал" and t["ret"] > 0.08)

# 7) согласованность капитала: equity = сумма реализованного PnL + старт
eq = st["cash"] + st["units"] * 105.0
realized = sum(x["pnl"] for x in st["trades"])
check(f"капитал сходится: {eq:.2f} ≈ {P.CAPITAL+realized:.2f}", abs(eq - (P.CAPITAL + realized)) < 0.01)

print("\nИТОГ:", "ВСЕ ТЕСТЫ ПРОЙДЕНЫ ✅" if ok else "ЕСТЬ ОШИБКИ ❌")
print(f"сделок: {len(st['trades'])}, капитал ${eq:.2f}")
