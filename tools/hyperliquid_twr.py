import json, csv, math, urllib.request
from collections import defaultdict
from datetime import datetime, timezone

ADDRESS="0x8bae3527e5a33fa0cf184f37bc112d071463ab6d"

req=urllib.request.Request(
    "https://api.hyperliquid.xyz/info",
    data=json.dumps({"type":"portfolio","user":ADDRESS}).encode(),
    headers={"Content-Type":"application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=30) as r:
    data=json.load(r)

sections={k:v for k,v in data}
sec=sections.get("allTime") or sections.get("perpAllTime")
av=sorted((int(t),float(v)) for t,v in sec["accountValueHistory"])
pnl=sorted((int(t),float(v)) for t,v in sec["pnlHistory"])
n=min(len(av),len(pnl))
series=[(max(ta,tp),a,p) for (ta,a),(tp,p) in zip(av[-n:],pnl[-n:])]

# Drop leading zero/non-positive account-value samples.
while series and series[0][1] <= 0:
    series.pop(0)
if len(series) < 2:
    raise RuntimeError("Insufficient positive-equity history")

def month_key(ts):
    return datetime.fromtimestamp(ts/1000, tz=timezone.utc).strftime("%Y-%m")

def calc_segment(rows):
    # Modified-Dietz/TWR-style interval returns using inferred net flows.
    # Net flow = account value change - trading PnL change.
    growth=1.0
    nav=1.0
    peak=1.0
    mdd=0.0
    total_pnl=0.0
    total_flow=0.0
    for i in range(1,len(rows)):
        _,a0,p0=rows[i-1]
        _,a1,p1=rows[i]
        dp=p1-p0
        flow=(a1-a0)-dp
        # Approximate intra-interval flow at midpoint. Samples are short-spaced.
        capital=a0 + 0.5*flow
        if capital > 0:
            r=dp/capital
            growth*=1+r
            nav*=1+r
            peak=max(peak,nav)
            mdd=min(mdd,(nav/peak-1)*100)
        total_pnl += dp
        total_flow += flow
    return {
        "return_pct": (growth-1)*100,
        "mdd_pct": mdd,
        "pnl": total_pnl,
        "net_flow": total_flow,
        "start_av": rows[0][1],
        "end_av": rows[-1][1],
    }

by_month=defaultdict(list)
for row in series:
    by_month[month_key(row[0])].append(row)

monthly=[]
for m in sorted(by_month):
    x=calc_segment(by_month[m])
    monthly.append([m,x["start_av"],x["end_av"],x["pnl"],x["net_flow"],x["return_pct"],x["mdd_pct"]])

overall=calc_segment(series)

with open("monthly_twr.csv","w",newline="") as f:
    w=csv.writer(f)
    w.writerow(["month_utc","start_account_value","end_account_value","trading_pnl","inferred_net_flow","cashflow_neutral_return_pct","cashflow_neutral_max_dd_pct"])
    w.writerows(monthly)

summary={
    "address":ADDRESS,
    "first_ts_utc":datetime.fromtimestamp(series[0][0]/1000,tz=timezone.utc).isoformat(),
    "last_ts_utc":datetime.fromtimestamp(series[-1][0]/1000,tz=timezone.utc).isoformat(),
    "start_account_value":series[0][1],
    "end_account_value":series[-1][1],
    "total_trading_pnl":overall["pnl"],
    "inferred_total_net_flow":overall["net_flow"],
    "cashflow_neutral_return_pct":overall["return_pct"],
    "cashflow_neutral_sampled_max_dd_pct":overall["mdd_pct"],
    "months":len(monthly),
}
with open("summary_twr.json","w") as f:
    json.dump(summary,f,indent=2)
with open("hyperliquid_portfolio.json","w") as f:
    json.dump(data,f,indent=2)

print("SUMMARY_TWR")
print(json.dumps(summary))
print("MONTHLY_TWR")
print(open("monthly_twr.csv").read())
