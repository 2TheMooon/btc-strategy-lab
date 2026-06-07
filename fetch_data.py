"""
Загрузка исторических данных BTC/USDT с Binance за последние 5 лет.
Сохраняет дневные (1d) и часовые (1h) свечи в папку data/.
"""
import time
import csv
import json
import os
import urllib.request
import urllib.parse

BASE = "https://api.binance.com/api/v3/klines"
SYMBOL = "BTCUSDT"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT_DIR, exist_ok=True)

YEARS = 5
NOW_MS = int(time.time() * 1000)
START_MS = NOW_MS - int(YEARS * 365.25 * 24 * 3600 * 1000)


def fetch_klines(symbol, interval, start_ms, end_ms):
    """Постранично тянем свечи forward от start_ms до end_ms (limit=1000)."""
    rows = []
    cur = start_ms
    while cur < end_ms:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": cur,
            "endTime": end_ms,
            "limit": 1000,
        }
        url = BASE + "?" + urllib.parse.urlencode(params)
        for attempt in range(5):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    batch = json.loads(r.read().decode())
                break
            except Exception as e:
                print(f"  retry {attempt+1} ({e})")
                time.sleep(2)
        else:
            raise RuntimeError("Не удалось получить данные после 5 попыток")
        if not batch:
            break
        rows.extend(batch)
        last_open = batch[-1][0]
        nxt = last_open + 1
        if nxt <= cur:
            break
        cur = nxt
        if len(batch) < 1000:
            break
        time.sleep(0.25)
    return rows


def save_csv(rows, path):
    """Сохраняем колонки: time(ms), open, high, low, close, volume."""
    seen = set()
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "open", "high", "low", "close", "volume"])
        for k in rows:
            t = int(k[0])
            if t in seen:
                continue
            seen.add(t)
            w.writerow([t, k[1], k[2], k[3], k[4], k[5]])
    return len(seen)


for interval in ("1d", "1h"):
    print(f"Загружаю {interval} ...")
    rows = fetch_klines(SYMBOL, interval, START_MS, NOW_MS)
    path = os.path.join(OUT_DIR, f"btc_{interval}.csv")
    n = save_csv(rows, path)
    print(f"  -> {n} свечей сохранено в {path}")

print("Готово.")
