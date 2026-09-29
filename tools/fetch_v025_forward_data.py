import csv, json, time, urllib.parse, urllib.request
from pathlib import Path
from datetime import datetime, timezone

SYMS = ["HYPE","AAVE","TAO","UNI","PENDLE","APT","ONDO","AKE","USELESS"]
START_MS = 1789776000000  # 2026-09-19 00:00 UTC
END_MS   = 1790640000000  # 2026-09-29 00:00 UTC exclusive
OUT = Path("forward_data")
OUT.mkdir(exist_ok=True)
HEADER = ["open_time","open","high","low","close","volume","close_time","quote_asset_volume","count","taker_buy_volume","taker_buy_quote_volume","ignore"]

def get_chunk(symbol, start_ms):
    params = urllib.parse.urlencode({
        "symbol": f"{symbol}USDT",
        "interval": "1m",
        "startTime": start_ms,
        "endTime": END_MS - 1,
        "limit": 1500,
    })
    url = "https://fapi.binance.com/fapi/v1/klines?" + params
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

manifest = {}
for sym in SYMS:
    rows = []
    cur = START_MS
    while cur < END_MS:
        got = get_chunk(sym, cur)
        if not got:
            raise RuntimeError(f"{sym}: empty response at {cur}")
        rows.extend(got)
        nxt = int(got[-1][0]) + 60000
        if nxt <= cur:
            raise RuntimeError(f"{sym}: non-advancing cursor")
        cur = nxt
        time.sleep(0.05)
    rows = [r for r in rows if START_MS <= int(r[0]) < END_MS]
    rows.sort(key=lambda r: int(r[0]))
    dedup = {}
    for r in rows:
        dedup[int(r[0])] = r[:12]
    rows = [dedup[k] for k in sorted(dedup)]
    expected = (END_MS - START_MS) // 60000
    if len(rows) != expected:
        missing = []
        have = set(dedup)
        for t in range(START_MS, END_MS, 60000):
            if t not in have:
                missing.append(t)
                if len(missing) >= 20:
                    break
        raise RuntimeError(f"{sym}: expected {expected} rows, got {len(rows)}; first missing={missing}")
    out = OUT / f"{sym}USDT_1m_2026-09-19_to_2026-09-28.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)
    manifest[sym] = {
        "rows": len(rows),
        "start_open_time": int(rows[0][0]),
        "end_open_time": int(rows[-1][0]),
        "file": str(out),
    }
(OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
print(json.dumps(manifest, indent=2))
