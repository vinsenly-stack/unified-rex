import json, csv, urllib.request
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

while series and series[0][1] <= 0:
    series.pop(0)
if len(series) < 2:
    raise RuntimeError("Insufficient positive-equity history")

def key(ts):
    return datetime.fromtimestamp(ts/1000,tz=timezone.utc).strftime("%Y-%m")

# Build cashflow-neutral interval returns. Each interval belongs to the month
# of its ending valuation, so month boundaries are included exactly once.
intervals=[]
for i in range(1,len(series)):
    t0,a0,p0=series[i-1]
    t1,a1,p1=series[i]
    dp=p1-p0
    flow=(a1-a0)-dp
    capital=a0+0.5*flow
    r=(dp/capital) if capital>0 else 0.0
    intervals.append((t1,key(t1),a0,a1,dp,flow,r))

def summarize(items):
    growth=1.0
    nav=1.0
    peak=1.0
    mdd=0.0
    pnl_sum=0.0
    flow_sum=0.0
    for _,_,_,_,dp,flow,r in items:
        growth*=1+r
        nav*=1+r
        peak=max(peak,nav)
        mdd=min(mdd,(nav/peak-1)*100)
        pnl_sum+=dp
        flow_sum+=flow
    return (growth-1)*100,mdd,pnl_sum,flow_sum

by_month=defaultdict(list)
for x in intervals:
    by_month[x[1]].append(x)

rows=[]
for m in sorted(by_month):
    arr=by_month[m]
    ret,mdd,pnl_sum,flow_sum=summarize(arr)
    rows.append([m,arr[0][2],arr[-1][3],pnl_sum,flow_sum,ret,mdd])

overall_ret,overall_dd,total_pnl,total_flow=summarize(intervals)

with open("monthly_twr.csv","w",newline="") as f:
    w=csv.writer(f)
    w.writerow(["month_utc","start_account_value","end_account_value","trading_pnl","inferred_net_flow","cashflow_neutral_return_pct","cashflow_neutral_max_dd_pct"])
    w.writerows(rows)

summary={
    "address":ADDRESS,
    "first_ts_utc":datetime.fromtimestamp(series[0][0]/1000,tz=timezone.utc).isoformat(),
    "last_ts_utc":datetime.fromtimestamp(series[-1][0]/1000,tz=timezone.utc).isoformat(),
    "start_account_value":series[0][1],
    "end_account_value":series[-1][1],
    "total_trading_pnl":total_pnl,
    "inferred_total_net_flow":total_flow,
    "cashflow_neutral_return_pct":overall_ret,
    "cashflow_neutral_sampled_max_dd_pct":overall_dd,
    "months":len(rows),
}
with open("summary_twr.json","w") as f:
    json.dump(summary,f,indent=2)
with open("hyperliquid_portfolio.json","w") as f:
    json.dump(data,f,indent=2)

print("SUMMARY_TWR")
print(json.dumps(summary))
print("MONTHLY_TWR")
print(open("monthly_twr.csv").read())
