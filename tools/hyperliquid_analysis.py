import json
import csv
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

ADDRESS = "0x8bae3527e5a33fa0cf184f37bc112d071463ab6d"

req = urllib.request.Request(
    "https://api.hyperliquid.xyz/info",
    data=json.dumps({"type": "portfolio", "user": ADDRESS}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=30) as r:
    data = json.load(r)

sections = {k: v for k, v in data}
sec = sections.get("allTime") or sections.get("perpAllTime")
if not sec:
    raise RuntimeError("No allTime/perpAllTime section")

av = sorted((int(t), float(v)) for t, v in sec.get("accountValueHistory", []))
pnl = sorted((int(t), float(v)) for t, v in sec.get("pnlHistory", []))
if not av or not pnl:
    raise RuntimeError("Missing account value or pnl history")

n = min(len(av), len(pnl))
av = av[-n:]
pnl = pnl[-n:]
series = [(max(ta, tp), a, p) for (ta, a), (tp, p) in zip(av, pnl)]

by_month = defaultdict(list)
for row in series:
    dt = datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc)
    by_month[dt.strftime("%Y-%m")].append(row)

def max_dd(values):
    values = [x for x in values if x > 0]
    if not values:
        return None
    peak = values[0]
    worst = 0.0
    for x in values:
        peak = max(peak, x)
        worst = min(worst, (x / peak - 1) * 100)
    return worst

rows = []
for month in sorted(by_month):
    arr = by_month[month]
    _, a0, p0 = arr[0]
    _, a1, p1 = arr[-1]
    month_pnl = p1 - p0
    ret = month_pnl / a0 * 100 if a0 > 0 else None
    adjusted_equity = [a0 + (p - p0) for _, _, p in arr]
    mdd = max_dd(adjusted_equity)
    rows.append([month, a0, a1, month_pnl, ret, mdd])

with open("monthly_pnl_adjusted.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "month_utc",
        "start_account_value",
        "end_account_value",
        "trading_pnl",
        "trading_return_pct",
        "cashflow_adjusted_max_dd_pct",
    ])
    w.writerows(rows)

base_a = series[0][1]
base_p = series[0][2]
overall_adjusted = [base_a + (p - base_p) for _, _, p in series]
overall_dd = max_dd(overall_adjusted)
total_pnl = series[-1][2] - base_p

summary = {
    "first_ts_utc": datetime.fromtimestamp(series[0][0] / 1000, tz=timezone.utc).isoformat(),
    "last_ts_utc": datetime.fromtimestamp(series[-1][0] / 1000, tz=timezone.utc).isoformat(),
    "start_account_value": base_a,
    "end_account_value": series[-1][1],
    "total_pnl_change": total_pnl,
    "pnl_return_on_initial_equity_pct": total_pnl / base_a * 100 if base_a > 0 else None,
    "cashflow_adjusted_sampled_max_dd_pct": overall_dd,
    "months": len(rows),
}

with open("summary.json", "w") as f:
    json.dump(summary, f, indent=2)
with open("hyperliquid_portfolio.json", "w") as f:
    json.dump(data, f, indent=2)

print("SUMMARY_JSON")
print(json.dumps(summary))
print("MONTHLY_CSV")
print(open("monthly_pnl_adjusted.csv").read())
