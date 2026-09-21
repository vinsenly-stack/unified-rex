import json, urllib.request, csv, math, statistics
from collections import defaultdict
from datetime import datetime, timezone

ADDRESS="0x8bae3527e5a33fa0cf184f37bc112d071463ab6d"
API="https://api.hyperliquid.xyz/info"

def post(payload):
    req=urllib.request.Request(API,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(req,timeout=30) as r:
        return json.load(r)

def ms(s):
    return int(datetime.fromisoformat(s.replace("Z","+00:00")).timestamp()*1000)

def fetch_fills(start,end,aggregate=True):
    out=[]
    cur=start
    while cur<=end:
        page=post({"type":"userFillsByTime","user":ADDRESS,"startTime":cur,"endTime":end,"aggregateByTime":aggregate})
        if not page: break
        out.extend(page)
        last=max(int(x["time"]) for x in page)
        if len(page)<2000 or last>=end: break
        cur=last+1
        if len(out)>12000: break
    # dedupe tids/hashes if possible
    seen=set(); ded=[]
    for x in sorted(out,key=lambda z:(int(z["time"]),str(z.get("tid","")),str(z.get("oid","")))):
        k=(x.get("tid"),x.get("hash"),x.get("oid"),x.get("time"),x.get("px"),x.get("sz"))
        if k in seen: continue
        seen.add(k); ded.append(x)
    return ded

portfolio=post({"type":"portfolio","user":ADDRESS})
sections={k:v for k,v in portfolio}
sec=sections.get("allTime") or sections.get("perpAllTime")
av=sorted((int(t),float(v)) for t,v in sec["accountValueHistory"])

def account_value_at(t):
    # nearest prior sample
    lo=0; hi=len(av)-1; ans=av[0][1]
    while lo<=hi:
        mid=(lo+hi)//2
        if av[mid][0]<=t:
            ans=av[mid][1]; lo=mid+1
        else: hi=mid-1
    return ans

windows=[
 ("2025-10","2025-10-01T00:00:00Z","2025-10-31T23:59:59Z"),
 ("2025-11","2025-11-01T00:00:00Z","2025-11-30T23:59:59Z"),
 ("2025-12","2025-12-01T00:00:00Z","2025-12-31T23:59:59Z"),
 ("2026-03","2026-03-01T00:00:00Z","2026-03-31T23:59:59Z"),
 ("2026-04","2026-04-01T00:00:00Z","2026-04-30T23:59:59Z"),
 ("2026-08","2026-08-01T00:00:00Z","2026-08-31T23:59:59Z"),
 ("2026-09","2026-09-01T00:00:00Z","2026-09-21T23:59:59Z"),
]
all_rows=[]
coverage=[]
for label,s,e in windows:
    fills=fetch_fills(ms(s),ms(e),True)
    coverage.append([label,len(fills), min([int(x["time"]) for x in fills],default=None), max([int(x["time"]) for x in fills],default=None)])
    for x in fills:
        x=dict(x); x["_window"]=label; all_rows.append(x)

# Also query last 10k horizon to determine oldest retained fill.
recent=fetch_fills(ms("2025-01-01T00:00:00Z"),ms("2026-09-21T23:59:59Z"),True)
oldest=min([int(x["time"]) for x in recent],default=None)
newest=max([int(x["time"]) for x in recent],default=None)

# Reconstruct position episodes from retained fills.
# startPosition is authoritative pre-fill position. signed fill = +sz for buy, -sz for sell.
episodes=[]
active={}
fills_sorted=sorted(all_rows,key=lambda x:int(x["time"]))
for x in fills_sorted:
    coin=x["coin"]; t=int(x["time"]); px=float(x["px"]); sz=float(x["sz"])
    sp=float(x.get("startPosition","0") or 0)
    signed=sz if x.get("side")=="B" else -sz
    ep=active.get(coin)
    # New episode if position before fill is flat or active missing/inconsistent.
    if abs(sp)<1e-12 or ep is None:
        ep={"coin":coin,"start":t,"end":t,"entry_side":"LONG" if signed>0 else "SHORT",
            "fills":[],"fees":0.0,"closed_pnl":0.0,"max_abs_pos":0.0,"max_notional":0.0,
            "maker":0,"taker":0,"twap":0}
        active[coin]=ep
    ep["fills"].append(x); ep["end"]=t
    ep["fees"]+=float(x.get("fee","0") or 0)
    ep["closed_pnl"]+=float(x.get("closedPnl","0") or 0)
    if x.get("crossed"): ep["taker"]+=1
    else: ep["maker"]+=1
    if x.get("twapId") not in (None,"","null"): ep["twap"]+=1
    pos_after=sp+signed
    ep["max_abs_pos"]=max(ep["max_abs_pos"],abs(sp),abs(pos_after))
    ep["max_notional"]=max(ep["max_notional"],abs(sp)*px,abs(pos_after)*px)
    # episode closes when position after fill flat; reversal ends old episode and begins new would be rare.
    if abs(pos_after)<1e-10:
        episodes.append(ep); active.pop(coin,None)

# Metrics by episode
ep_rows=[]
for ep in episodes:
    start=ep["start"]; end=ep["end"]; dur=(end-start)/3600000
    av0=account_value_at(start)
    roi=ep["closed_pnl"]/av0*100 if av0 else None
    lev=ep["max_notional"]/av0 if av0 else None
    ep_rows.append({
        "coin":ep["coin"],"side":ep["entry_side"],"start":start,"end":end,"hours":dur,
        "fills":len(ep["fills"]),"closed_pnl":ep["closed_pnl"],"fees":ep["fees"],
        "pnl_pct_equity":roi,"max_notional":ep["max_notional"],"max_notional_equity_x":lev,
        "maker_share":ep["maker"]/len(ep["fills"]) if ep["fills"] else None,
        "twap_share":ep["twap"]/len(ep["fills"]) if ep["fills"] else None,
    })

def dt(t):
    return datetime.fromtimestamp(t/1000,tz=timezone.utc).isoformat() if t else ""

# Save coverage
with open("fill_coverage.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["window","fills","first_fill","last_fill"])
    for label,n,a,b in coverage:w.writerow([label,n,dt(a),dt(b)])
    w.writerow(["recent_retained_total",len(recent),dt(oldest),dt(newest)])

with open("episodes.csv","w",newline="") as f:
    fields=list(ep_rows[0].keys()) if ep_rows else ["coin"]
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
    for r in ep_rows:
        q=dict(r); q["start"]=dt(r["start"]); q["end"]=dt(r["end"]); w.writerow(q)

# Summaries for fully closed episodes
summary={}
if ep_rows:
    by_coin=defaultdict(list); by_month=defaultdict(list); by_side=defaultdict(list)
    for r in ep_rows:
        by_coin[r["coin"]].append(r)
        by_month[datetime.fromtimestamp(r["start"]/1000,tz=timezone.utc).strftime("%Y-%m")].append(r)
        by_side[r["side"]].append(r)
    def agg(group):
        n=len(group); pnls=[r["closed_pnl"] for r in group]
        wins=sum(p>0 for p in pnls)
        pos=sum(p for p in pnls if p>0); neg=-sum(p for p in pnls if p<0)
        return {"episodes":n,"pnl":sum(pnls),"win_rate":wins/n if n else None,
                "pf":pos/neg if neg>0 else None,
                "median_hours":statistics.median([r["hours"] for r in group]) if n else None,
                "median_leverage_x":statistics.median([r["max_notional_equity_x"] for r in group if r["max_notional_equity_x"] is not None]) if n else None,
                "maker_share":sum(r["maker_share"] for r in group)/n if n else None}
    summary={
      "retained_fill_count":len(recent),
      "oldest_retained_fill":dt(oldest),
      "newest_retained_fill":dt(newest),
      "closed_episodes":len(ep_rows),
      "by_coin":{k:agg(v) for k,v in sorted(by_coin.items(),key=lambda kv:-sum(x["closed_pnl"] for x in kv[1]))},
      "by_month":{k:agg(v) for k,v in sorted(by_month.items())},
      "by_side":{k:agg(v) for k,v in by_side.items()},
      "top_winners":sorted(ep_rows,key=lambda r:r["closed_pnl"],reverse=True)[:25],
      "top_losers":sorted(ep_rows,key=lambda r:r["closed_pnl"])[:25],
    }
with open("trade_forensics_summary.json","w") as f: json.dump(summary,f,indent=2,default=str)

print("COVERAGE")
print(open("fill_coverage.csv").read())
print("SUMMARY")
print(json.dumps(summary))
