import json, urllib.request, math
from datetime import datetime, timezone

API="https://api.hyperliquid.xyz/info"
ADDRESS="0x8bae3527e5a33fa0cf184f37bc112d071463ab6d"

def post(payload):
    req=urllib.request.Request(API,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(req,timeout=30) as r:
        return json.load(r)

def candle(coin,start,end):
    return post({"type":"candleSnapshot","req":{"coin":coin,"interval":"4h","startTime":start,"endTime":end}})

episodes=[
 ("BTC_2025", "BTC", 1760074367022,1762878142375),
 ("GAS_2025","GAS",1760504948992,1762176251764),
 ("NOT_2025","NOT",1765297735191,1765298481771),
 ("ETH_SHORT_LOSS_2025","ETH",1764996396293,1765297305782),
 ("CL_2026","xyz:CL",1772872831186,1773024962830),
 ("INTC_2026","cash:INTC",1776042289891,1777644338619),
 ("RSR_2026","RSR",1787283391102,1787623436229),
 ("S_2026","S",1787645378890,1787775095535),
]

def fill_near(coin,t):
    a=post({"type":"userFillsByTime","user":ADDRESS,"startTime":t-60000,"endTime":t+60000,"aggregateByTime":True})
    a=[x for x in a if x["coin"]==coin]
    return min(a,key=lambda x:abs(int(x["time"])-t)) if a else None

def ret(a,b):
    return (b/a-1)*100 if a else None

out=[]
for label,coin,start,end in episodes:
    f=fill_near(coin,start)
    entry=float(f["px"]) if f else None
    side=("LONG" if (f and f.get("side")=="B") else "SHORT" if f else None)
    try:
        cs=candle(coin,start-10*24*3600*1000,start+24*3600*1000)
    except Exception as e:
        out.append({"label":label,"coin":coin,"error":str(e)});continue
    cs=sorted(cs,key=lambda x:int(x["t"]))
    before=[x for x in cs if int(x["T"])<start]
    if len(before)<42:
        out.append({"label":label,"coin":coin,"entry":entry,"side":side,"candles":len(before),"error":"insufficient_candles"});continue
    close=[float(x["c"]) for x in before]
    high=[float(x["h"]) for x in before]
    low=[float(x["l"]) for x in before]
    vols=[float(x["v"]) for x in before]
    last=close[-1]
    def prior(n):
        return ret(close[-1-n],last) if len(close)>n else None
    hi7=max(high[-42:]); lo7=min(low[-42:])
    range_pos=(entry-lo7)/(hi7-lo7) if entry and hi7>lo7 else None
    # 4h true-range proxy
    trs=[high[i]-low[i] for i in range(max(0,len(high)-42),len(high))]
    atr=sum(trs[-6:])/min(6,len(trs)) if trs else None
    atr_base=sum(trs[-30:])/min(30,len(trs)) if trs else None
    vol6=sum(vols[-6:])/6 if len(vols)>=6 else None
    vol30=sum(vols[-30:])/30 if len(vols)>=30 else None
    # nearest post-entry and pre-exit fill prices
    ff=post({"type":"userFillsByTime","user":ADDRESS,"startTime":end-60000,"endTime":end+60000,"aggregateByTime":True})
    ff=[x for x in ff if x["coin"]==coin]
    exitpx=float(min(ff,key=lambda x:abs(int(x["time"])-end))["px"]) if ff else None
    out.append({
      "label":label,"coin":coin,"side":side,
      "entry_time":datetime.fromtimestamp(start/1000,tz=timezone.utc).isoformat(),
      "exit_time":datetime.fromtimestamp(end/1000,tz=timezone.utc).isoformat(),
      "entry_px":entry,"exit_px":exitpx,
      "asset_move_entry_exit_pct":ret(entry,exitpx) if entry and exitpx else None,
      "prior_4h_pct":prior(1),"prior_12h_pct":prior(3),"prior_24h_pct":prior(6),"prior_3d_pct":prior(18),"prior_7d_pct":prior(42),
      "entry_7d_range_pos":range_pos,
      "atr_4h_recent_vs_30_ratio":atr/atr_base if atr_base else None,
      "volume_24h_vs_5d_ratio":vol6/vol30 if vol30 else None,
    })

print("ENTRY_CONTEXT")
print(json.dumps(out))
with open("entry_context.json","w") as f:json.dump(out,f,indent=2)
