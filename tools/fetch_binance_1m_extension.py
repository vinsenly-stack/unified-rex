from __future__ import annotations
import csv, io, json, time, urllib.request, zipfile
from datetime import date, timedelta
from pathlib import Path

SYMBOLS = ["HYPEUSDT","AAVEUSDT","TAOUSDT","UNIUSDT","PENDLEUSDT","APTUSDT","ONDOUSDT","AKEUSDT","USELESSUSDT"]
START = date(2026,9,19)
END = date(2026,9,29)  # exclusive
OUT = Path("data/binance_ext")
OUT.mkdir(parents=True, exist_ok=True)
COLS = ["open_time","open","high","low","close","volume","close_time","quote_asset_volume","count","taker_buy_volume","taker_buy_quote_volume","ignore"]

def dates():
    d=START
    while d<END:
        yield d
        d += timedelta(days=1)

def fetch_bytes(url):
    last=None
    for attempt in range(6):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req,timeout=45) as r:
                return r.read()
        except Exception as e:
            last=e
            time.sleep(2**attempt)
    raise RuntimeError(f"failed {url}: {last}")

def fetch_symbol(sym):
    outrows=[]
    for d in dates():
        ds=d.isoformat()
        url=f"https://data.binance.vision/data/futures/um/daily/klines/{sym}/1m/{sym}-1m-{ds}.zip"
        b=fetch_bytes(url)
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            names=z.namelist()
            if len(names)!=1:
                raise RuntimeError(f"{sym} {ds} unexpected archive {names}")
            raw=z.read(names[0]).decode("utf-8")
        rr=list(csv.reader(io.StringIO(raw)))
        if rr and rr[0] and rr[0][0].lower()=="open_time":
            rr=rr[1:]
        outrows.extend(r[:12] for r in rr if r and r[0].isdigit())
        print(json.dumps({"symbol":sym,"date":ds,"rows":len(rr)}),flush=True)
    # dedupe and chronological
    m={int(r[0]):r for r in outrows}
    keys=sorted(m)
    out=OUT/f"{sym}_1m_2026-09-19_to_2026-09-28.csv"
    with out.open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(COLS)
        for k in keys: w.writerow(m[k])
    expected=10*1440
    gaps=sum(1 for a,b in zip(keys,keys[1:]) if b-a!=60_000)
    meta={"symbol":sym,"rows":len(keys),"expected_rows":expected,"gaps":gaps,
          "first_open_time":keys[0] if keys else None,"last_open_time":keys[-1] if keys else None}
    print("SUMMARY",json.dumps(meta),flush=True)
    return meta

meta=[fetch_symbol(s) for s in SYMBOLS]
manifest={"source":"data.binance.vision USD-M daily klines","interval":"1m",
          "start_utc":"2026-09-19T00:00:00Z","end_exclusive_utc":"2026-09-29T00:00:00Z",
          "symbols":meta}
(OUT/"MANIFEST.json").write_text(json.dumps(manifest,indent=2))
if any(m["rows"]!=m["expected_rows"] or m["gaps"]!=0 for m in meta):
    raise SystemExit("validation failed")
