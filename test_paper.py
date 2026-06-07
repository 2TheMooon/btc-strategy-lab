"""Self-test of the live-trading logic: entry, stop-loss, re-arm, exit by signal."""
import datetime
import pandas as pd
import paper_trade as P

cur_sig = {"v": 0}
cfg = {"key": "t", "base": "test", "tf": "hourly", "stop": True, "color": "#fff",
       "atr_n": 24, "k": 2.5,
       "fn": lambda df: pd.Series([cur_sig["v"]] * len(df), index=df.index)}
st = P.new_strat_state()

base = [(101, 99, 100)] * 30  # high, low, close — range 2 => ATR ~ 2 => stop = 100-2.5*2 = 95


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
    print(("  OK   " if cond else " FAIL ") + name)


# 1) entry
run(dfh_from([(101, 99, 100)]), 100.0, 1, t0)
sp = st["open_trade"]["stop_price"] if st["open_trade"] else None
check(f"entry opened, position=1, stop~95 (={round(sp,1) if sp else None})",
      st["position"] == 1 and sp is not None and abs(sp - 95) < 0.6)

# 2) stop-loss: a bar with low=94 < 95
run(dfh_from([(101, 99, 100), (96, 94, 95)]), 95.0, 1, t0 + datetime.timedelta(hours=2))
check("stop triggered: position=0, reason='stop', armed=False",
      st["position"] == 0 and len(st["trades"]) == 1 and st["trades"][-1]["reason"] == "stop" and not st["armed"])

# 3) signal=1 but armed=False -> no re-entry
run(dfh_from([(101, 99, 100), (96, 94, 95), (96, 94, 95)]), 95.0, 1, t0 + datetime.timedelta(hours=3))
check("no re-entry after stop (armed block)", st["position"] == 0)

# 4) signal=0 -> re-arm
run(dfh_from([(101, 99, 100), (96, 94, 95), (96, 94, 95)]), 95.0, 0, t0 + datetime.timedelta(hours=4))
check("re-arm: armed=True", st["armed"] is True and st["position"] == 0)

# 5) signal=1 -> re-entry
run(dfh_from([(101, 99, 100), (96, 94, 95), (96, 94, 95)]), 95.0, 1, t0 + datetime.timedelta(hours=5))
check("re-entry: position=1", st["position"] == 1)

# 6) signal=0 at price 105 -> exit by signal with profit (entry was 95)
run(dfh_from([(101, 99, 100), (96, 94, 95), (96, 94, 95), (106, 104, 105)]), 105.0, 0, t0 + datetime.timedelta(hours=6))
t = st["trades"][-1]
check(f"exit by signal with profit (ret={t['ret']*100:.1f}%)",
      st["position"] == 0 and t["reason"] == "signal" and t["ret"] > 0.08)

# 7) capital consistency: equity = realized PnL + start
eq = st["cash"] + st["units"] * 105.0
realized = sum(x["pnl"] for x in st["trades"])
check(f"capital reconciles: {eq:.2f} ~ {P.CAPITAL+realized:.2f}", abs(eq - (P.CAPITAL + realized)) < 0.01)

print("\nRESULT:", "ALL TESTS PASSED" if ok else "FAILURES PRESENT")
print(f"trades: {len(st['trades'])}, capital ${eq:.2f}")
