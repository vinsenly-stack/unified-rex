import json, urllib.request, csv, statistics
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

def iso(t):
    return datetime.fromtimestamp(t/1000,tz=timezone.utc).isoformat()

def month(t):
    return datetime.fromtimestamp(t/1000,tz=timezone.utc).strftime("%Y-%m")

def fetch_fills(start,end,aggregate=True):
    out=[]; cur=start
    while cur<=end:
        page=post({"type":"userFillsByTime","user":ADDRESS,"startTime":cur,"endTime":end,"aggregateByTime":aggregate})
        if not page: break
        out.extend(page)
        last=max(int(x["time"]) for x in page)
        if len(page)<2000 or last>=end: break
        cur=last+1
        if len(out)>12000: break
    seen=set(); ded=[]
    for x in sorted(out,key=lambda z:(int(z["time"]),str(z.get("tid","")),str(z.get("oid","")))):
        k=(x.get("tid"),x.get("hash"),x.get("oid"),x.get("time"),x.get("px"),x.get("sz"))
        if k not in seen:
            seen.add(k); ded.append(x)
    return ded

portfolio=post({"type":"portfolio","user":ADDRESS})
sec=dict(portfolio).get("allTime") or dict(portfolio).get("perpAllTime")
av=sorted((int(t),float(v)) for t,v in sec["accountValueHistory"])

def account_value_at(t):
    lo=0; hi=len(av)-1; ans=av[0][1]
    while lo<=hi:
        mid=(lo+hi)//2
        if av[mid][0]<=t: ans=av[mid][1]; lo=mid+1
        else: hi=mid-1
    return ans

fills=fetch_fills(ms("2025-01-01T00:00:00Z"),ms("2026-09-21T23:59:59Z"),True)

# Reconstruct complete flat-to-flat episodes only.
episodes=[]; active={}; skip_until_flat=set()
for x in sorted(fills,key=lambda z:int(z["time"])):
    coin=x["coin"]; t=int(x["time"]); px=float(x["px"]); sz=float(x["sz"])
    sp=float(x.get("startPosition","0") or 0)
    signed=sz if x.get("side")=="B" else -sz
    pa=sp+signed

    if coin in skip_until_flat:
        if abs(pa)<1e-10: skip_until_flat.remove(coin)
        continue

    if coin not in active:
        if abs(sp)>=1e-10:
            # episode started before retained tape
            if abs(pa)>=1e-10: skip_until_flat.add(coin)
            continue
        active[coin]={
            "coin":coin,"start":t,"end":t,"entry_side":"LONG" if signed>0 else "SHORT",
            "fills":[],"closed_pnl":0.0,"fees":0.0,"max_notional":0.0,
            "maker":0,"taker":0,"adds":0,"reductions":0,"proof_adds":0,"pullback_adds":0,
            "entry_px":px,"initial_notional":abs(pa)*px,"peak_pos_time":t
        }

    ep=active[coin]
    before=abs(sp); after=abs(pa)
    if after>before+1e-12:
        ep["adds"]+=1
        favorable=(px>ep["entry_px"]) if ep["entry_side"]=="LONG" else (px<ep["entry_px"])
        if favorable: ep["proof_adds"]+=1
        else: ep["pullback_adds"]+=1
    elif after<before-1e-12:
        ep["reductions"]+=1

    ep["fills"].append(x); ep["end"]=t
    ep["closed_pnl"]+=float(x.get("closedPnl","0") or 0)
    ep["fees"]+=float(x.get("fee","0") or 0)
    ep["maker"]+=0 if x.get("crossed") else 1
    ep["taker"]+=1 if x.get("crossed") else 0
    cur_notional=max(abs(sp)*px,abs(pa)*px)
    if cur_notional>ep["max_notional"]:
        ep["max_notional"]=cur_notional; ep["peak_pos_time"]=t

    if abs(pa)<1e-10:
        episodes.append(ep); active.pop(coin,None)

rows=[]
for ep in episodes:
    av0=account_value_at(ep["start"])
    nf=len(ep["fills"])
    rows.append({
        "coin":ep["coin"],"side":ep["entry_side"],"start":ep["start"],"end":ep["end"],
        "start_month":month(ep["start"]),"close_month":month(ep["end"]),
        "hours":(ep["end"]-ep["start"])/3600000,"fills":nf,
        "closed_pnl":ep["closed_pnl"],"fees":ep["fees"],
        "pnl_pct_equity":ep["closed_pnl"]/av0*100 if av0 else None,
        "initial_notional_equity_x":ep["initial_notional"]/av0 if av0 else None,
        "max_notional_equity_x":ep["max_notional"]/av0 if av0 else None,
        "scale_multiple":ep["max_notional"]/ep["initial_notional"] if ep["initial_notional"]>0 else None,
        "maker_share":ep["maker"]/nf if nf else None,
        "adds":ep["adds"],"reductions":ep["reductions"],
        "proof_add_share":ep["proof_adds"]/ep["adds"] if ep["adds"] else None,
        "pullback_add_share":ep["pullback_adds"]/ep["adds"] if ep["adds"] else None,
        "peak_pos_hours":(ep["peak_pos_time"]-ep["start"])/3600000,
    })

def agg(g):
    if not g:return {}
    pn=[x["closed_pnl"] for x in g]; pos=sum(x for x in pn if x>0); neg=-sum(x for x in pn if x<0)
    lev=[x["max_notional_equity_x"] for x in g if x["max_notional_equity_x"] is not None]
    scales=[x["scale_multiple"] for x in g if x["scale_multiple"] is not None]
    return {
      "episodes":len(g),"pnl":sum(pn),"win_rate":sum(x>0 for x in pn)/len(g),
      "pf":pos/neg if neg>0 else None,
      "median_hours":statistics.median(x["hours"] for x in g),
      "median_max_notional_equity_x":statistics.median(lev) if lev else None,
      "median_scale_multiple":statistics.median(scales) if scales else None,
      "maker_share":sum(x["maker_share"] for x in g)/len(g),
      "proof_add_share":sum((x["proof_add_share"] or 0)*x["adds"] for x in g)/sum(x["adds"] for x in g) if sum(x["adds"] for x in g) else None,
      "pullback_add_share":sum((x["pullback_add_share"] or 0)*x["adds"] for x in g)/sum(x["adds"] for x in g) if sum(x["adds"] for x in g) else None,
    }

by_close_month=defaultdict(list); by_start_month=defaultdict(list); by_coin=defaultdict(list); by_side=defaultdict(list)
for r in rows:
    by_close_month[r["close_month"]].append(r); by_start_month[r["start_month"]].append(r)
    by_coin[r["coin"]].append(r); by_side[r["side"]].append(r)

target_months={"2025-10","2025-11","2025-12","2026-03","2026-04","2026-08"}
month_coin={}
for m in sorted(target_months):
    g=by_close_month.get(m,[])
    bc=defaultdict(list)
    for r in g:bc[r["coin"]].append(r)
    month_coin[m]=[{**{"coin":c},**agg(v)} for c,v in sorted(bc.items(),key=lambda kv:-sum(x["closed_pnl"] for x in kv[1]))]

top_by_month={}
for m in sorted(target_months):
    g=by_close_month.get(m,[])
    top_by_month[m]=sorted(g,key=lambda x:x["closed_pnl"],reverse=True)[:10]

out={
 "retained_fill_count":len(fills),
 "oldest_fill":iso(min(int(x["time"]) for x in fills)),
 "newest_fill":iso(max(int(x["time"]) for x in fills)),
 "complete_closed_episodes":len(rows),
 "overall":agg(rows),
 "by_side":{k:agg(v) for k,v in by_side.items()},
 "by_close_month":{k:agg(v) for k,v in sorted(by_close_month.items())},
 "month_coin":month_coin,
 "top_by_month":top_by_month,
 "top_winners":sorted(rows,key=lambda x:x["closed_pnl"],reverse=True)[:30],
 "top_losers":sorted(rows,key=lambda x:x["closed_pnl"])[:20],
}
with open("trade_forensics_full.json","w") as f:json.dump(out,f,indent=2)
with open("episodes_full.csv","w",newline="") as f:
    if rows:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys()));w.writeheader()
        for r in rows:
            q=dict(r);q["start"]=iso(r["start"]);q["end"]=iso(r["end"]);w.writerow(q)

print("FORENSICS_FULL")
print(json.dumps(out))
