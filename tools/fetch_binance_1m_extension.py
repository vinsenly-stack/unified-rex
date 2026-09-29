from __future__ import annotations
import csv, json, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

SYMBOLS = ["HYPEUSDT","AAVEUSDT","TAOUSDT","UNIUSDT","PENDLEUSDT","APTUSDT","ONDOUSDT","AKEUSDT","USELESSUSDT"]
START = datetime(2026,9,19,tzinfo=timezone.utc)
END = datetime(2026,9,29,tzinfo=timezone.utc)  # exclusive; covers through Sep 28 23:59 UTC
OUT = Path("data/binance_ext")
OUT.mkdir(parents=True, exist_ok=True)

cols = ["open_time","open","high","low","close","volume","close_time","quote_asset_volume","count","taker_buy_volume","taker_buy_quote_volume","ignore"]

def ms(dt): return int(dt.timestamp()*1000)

def fetch_symbol(sym):
    start = ms(START); end = ms(END)-1
    rows = []
    cur = start
    while cur <= end:
        q = urllib.parse.urlencode({
            "symbol": sym, "interval": "1m", "startTime": cur,
            "endTime": end, "limit": 1500
        })
        url = "https://fapi.binance.com/fapi/v1/klines?" + q
        last_err = None
        for attempt in range(6):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    batch = json.loads(r.read().decode("utf-8"))
                break
            except Exception as e:
                last_err = e
                time.sleep(2**attempt)
        else:
            raise RuntimeError(f"{sym} failed at {cur}: {last_err}")
        if not batch: break
        rows.extend(batch)
        nxt = int(batch[-1][0]) + 60_000
        if nxt <= cur: raise RuntimeError("non-advancing cursor")
        cur = nxt
        time.sleep(0.05)

    # exact requested window + unique chronological
    d = {}
    for r in rows:
        ot = int(r[0])
        if start <= ot <= end:
            d[ot] = r[:12]
    keys = sorted(d)
    out = OUT / f"{sym}_1m_2026-09-19_to_2026-09-28.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(cols)
        for k in keys: w.writerow(d[k])

    expected = int((END-START).total_seconds()//60)
    gaps = sum(1 for a,b in zip(keys,keys[1:]) if b-a != 60_000)
    meta = {"symbol":sym,"rows":len(keys),"expected_rows":expected,"gaps":gaps,
            "first_open_time":keys[0] if keys else None,"last_open_time":keys[-1] if keys else None}
    print(json.dumps(meta), flush=True)
    return meta

all_meta = [fetch_symbol(s) for s in SYMBOLS]
(OUT/"MANIFEST.json").write_text(json.dumps({
    "source":"Binance USD-M Futures REST /fapi/v1/klines",
    "interval":"1m","start_utc":START.isoformat(),"end_exclusive_utc":END.isoformat(),
    "symbols":all_meta
}, indent=2))
if any(m["rows"] != m["expected_rows"] or m["gaps"] != 0 for m in all_meta):
    raise SystemExit("validation failed")
