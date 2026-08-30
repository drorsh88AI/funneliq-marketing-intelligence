# -*- coding: utf-8 -*-
import argparse
import hashlib, sys, json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import numpy as np

# The exact SHA-256 the phase 0 findings (docs/planning/PHASE0.md) are valid
# against. Every check in this script assumes the CSV matches this hash.
EXPECTED_SHA256 = "8ac67d50a6f96a8ece8abd770a5a1901b34036a5c98656455eb04cee07d707aa"

# Portable path: <PROJECT_ROOT>/funnel_marketing_data.csv, resolved relative
# to this file (scripts/ -> project root) unless overridden by --csv. The CSV
# is git-ignored and must be present locally; it does not ship with the repo.
DEFAULT_CSV = Path(__file__).resolve().parent.parent / "funnel_marketing_data.csv"

parser = argparse.ArgumentParser(description="Re-run the phase 0 data verification.")
parser.add_argument("--csv", type=Path, default=DEFAULT_CSV,
                     help=f"Path to funnel_marketing_data.csv (default: {DEFAULT_CSV})")
args = parser.parse_args()
CSV = args.csv

if not CSV.is_file():
    print(f"ERROR: CSV not found at {CSV}", file=sys.stderr)
    print("The source CSV is git-ignored and is not part of the repo.", file=sys.stderr)
    print("Place funnel_marketing_data.csv there, or pass --csv PATH.", file=sys.stderr)
    print(f"Expected SHA-256: {EXPECTED_SHA256}", file=sys.stderr)
    sys.exit(2)

out = {}

# ---- section A: fingerprint ----
with open(CSV, "rb") as f:
    raw = f.read()
out["sha256"] = hashlib.sha256(raw).hexdigest()
out["size_bytes"] = len(raw)
out["measured_at_utc"] = datetime.now(timezone.utc).isoformat()

if out["sha256"] != EXPECTED_SHA256:
    print(f"ERROR: SHA-256 mismatch for {CSV}", file=sys.stderr)
    print(f"  expected: {EXPECTED_SHA256}", file=sys.stderr)
    print(f"  measured: {out['sha256']}", file=sys.stderr)
    print("The findings in docs/planning/PHASE0.md are valid only against the "
          "expected hash above; this file is not that CSV.", file=sys.stderr)
    sys.exit(3)

df = pd.read_csv(CSV)
out["n_rows"] = len(df)
out["n_cols"] = df.shape[1]
out["columns"] = list(df.columns)

R = {}  # results dict: claim -> {expected, measured, pass, expr}
def check(name, expected, measured, expr, tol=None):
    if tol is not None and isinstance(expected,(int,float)) and isinstance(measured,(int,float)):
        ok = abs(expected-measured) <= tol
    else:
        ok = (expected == measured)
    R[name] = {"expected": expected, "measured": measured, "pass": bool(ok), "expr": expr}

# ---- section B: numeric claims ----
check("shape_rows", 3500, len(df), "len(df)")
check("shape_cols", 19, df.shape[1], "df.shape[1]")

ltv_missing = int(df["ltv_months"].isna().sum())
cp_missing = int(df["cumulative_profit"].isna().sum())
any_missing_rows = int(df[["ltv_months","cumulative_profit"]].isna().any(axis=1).sum())
check("ltv_months_missing", 4, ltv_missing, 'df["ltv_months"].isna().sum()')
check("cumulative_profit_missing", 29, cp_missing, 'df["cumulative_profit"].isna().sum()')
check("rows_with_any_missing", 33, any_missing_rows, 'df[["ltv_months","cumulative_profit"]].isna().any(axis=1).sum()')

upsell_rate_all = float(df["upsell"].mean()*100)
referred_yes_rate_all = float((df["referred"]=="Yes").mean()*100)
purchased_rate_all = float(df["purchased"].mean()*100)
purchased_count = int(df["purchased"].sum())
check("upsell_rate_all_pct", 42, round(upsell_rate_all,1), 'df["upsell"].mean()*100', tol=0.5)
check("referred_yes_rate_all_pct", 39, round(referred_yes_rate_all,1), '(df.referred=="Yes").mean()*100', tol=0.5)
check("purchased_rate_all_pct", 90, round(purchased_rate_all,1), 'df["purchased"].mean()*100', tol=0.5)
check("purchased_count", 3163, purchased_count, 'df["purchased"].sum()')

check("ad_budget_min", 500, int(df["ad_budget"].min()), 'df.ad_budget.min()')
check("ad_budget_max", 20000, int(df["ad_budget"].max()), 'df.ad_budget.max()')
check("ad_budget_median", 3000, float(df["ad_budget"].median()), 'df.ad_budget.median()')
check("ltv_months_min", 1, int(df["ltv_months"].min()), 'df.ltv_months.min()')
check("ltv_months_max", 56, int(df["ltv_months"].max()), 'df.ltv_months.max()')
check("ltv_months_mean", 22, round(float(df["ltv_months"].mean())), 'round(df.ltv_months.mean())')

# ---- invariants ----
id1 = (df["leads_answered"] + df["leads_not_answered"] == df["num_leads"])
check("identity_leads_pct", 100.0, round(float(id1.mean()*100),2), '(leads_answered+leads_not_answered==num_leads).mean()*100')

mono = (df["leads_answered"] >= df["followup_1"]) & (df["followup_1"] >= df["followup_2"]) & \
       (df["followup_2"] >= df["followup_3"]) & (df["followup_3"] >= df["followup_4"]) & \
       (df["followup_4"] >= df["followup_5"])
check("monotonic_violations", 0, int((~mono).sum()), "count of rows violating monotonic funnel chain")

id2 = (df["closed"] + df["not_closed"] == df["followup_5"])
check("closing_identity_violations", 0, int((~id2).sum()), "(closed+not_closed==followup_5) violations")

numeric_cols = df.select_dtypes(include=[np.number]).columns
neg_count = int((df[numeric_cols] < 0).sum().sum())
check("negative_values_count", 0, neg_count, "(df[numeric_cols]<0).sum().sum()")

check("num_leads_zero_count", 0, int((df["num_leads"]==0).sum()), "(df.num_leads==0).sum()")
check("referred_clean", True, bool(set(df["referred"].unique()) <= {"Yes","No"}), 'set(df.referred.unique()) <= {"Yes","No"}')

discrete_budgets = sorted(df["ad_budget"].unique().tolist())
expected_budgets = [500,800,1000,1500,2000,2500,3000,4000,5000,6000,7000,8000,10000,12000,15000,20000]
check("discrete_budget_values", expected_budgets, discrete_budgets, "sorted(df.ad_budget.unique())")
gap_rows = int(df[(df["ad_budget"]>=1501) & (df["ad_budget"]<=1999)].shape[0])
check("gap_1501_1999_empty", 0, gap_rows, "df[(ad_budget>=1501)&(ad_budget<=1999)].shape[0]")

# ---- dropout by stage (two candidate formulas) ----
stages = ["leads_answered","followup_1","followup_2","followup_3","followup_4","followup_5"]
sums = {s: df[s].sum() for s in stages}
dropout_agg = []
for i in range(1,6):
    prev, cur = sums[stages[i-1]], sums[stages[i]]
    dropout_agg.append(round((1 - cur/prev)*100,1))
expected_dropout = [21.7,25.7,18.6,10.4,29.2]
check("dropout_by_stage_aggregate", expected_dropout, dropout_agg,
      "1 - sum(stage_i)/sum(stage_i-1), stages=[leads_answered,fu1..fu5]")

dropout_mean = []
for i in range(1,6):
    prev_col, cur_col = stages[i-1], stages[i]
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(df[prev_col]>0, 1 - df[cur_col]/df[prev_col], np.nan)
    dropout_mean.append(round(float(np.nanmean(ratio))*100,1))
R["dropout_by_stage_per_row_mean_alt"] = {"expected": expected_dropout, "measured": dropout_mean,
    "pass": dropout_mean==expected_dropout, "expr": "mean over rows of (1 - cur/prev), alt formula for comparison"}

# ---- calls_to_closed record-level (purchased=1 population) ----
pur = df[df["purchased"]==1]
n_pur = len(pur)
mask_ge4 = pur["calls_to_closed"] >= 4
check("purchased_calls_ge4_count", 1519, int(mask_ge4.sum()), "df[purchased==1 & calls_to_closed>=4].shape[0]")
check("purchased_calls_ge4_pct", 48.0, round(float(mask_ge4.mean()*100),1), "mean(calls_to_closed>=4 | purchased==1)*100")
check("purchased_n", 3163, n_pur, "len(df[purchased==1])")

closed1 = pur[pur["closed"]==1]
closed2p = pur[pur["closed"]>=2]
check("closed_eq1_n", 488, len(closed1), "len(pur[closed==1])  # within purchased==1 population")
check("closed_ge2_n", 2675, len(closed2p), "len(pur[closed>=2])  # within purchased==1 population")
c1_ge4 = int((closed1["calls_to_closed"]>=4).sum())
check("closed_eq1_calls_ge4_count", 439, c1_ge4, "pur[closed==1 & calls_to_closed>=4].shape[0]")
check("closed_eq1_calls_ge4_pct", 89.96, round(c1_ge4/len(closed1)*100,2), "count/len(closed1)*100")

check("closed1_calls_mean", 5.65, round(float(closed1["calls_to_closed"].mean()),2), "closed1.calls_to_closed.mean()", tol=0.01)
check("closed2p_calls_mean", 3.35, round(float(closed2p["calls_to_closed"].mean()),2), "closed2p.calls_to_closed.mean()", tol=0.01)
check("closed1_leads_median", 20.5, float(closed1["num_leads"].median()), "closed1.num_leads.median() (row-level; weight=1 trivially since closed==1)")
check("closed1_budget_median", 1000, float(closed1["ad_budget"].median()), "closed1.ad_budget.median() (row-level; weight=1 trivially since closed==1)")
check("closed1_ltv_mean", 11.05, round(float(closed1["ltv_months"].mean()),2), "closed1.ltv_months.mean()", tol=0.01)
check("closed2p_ltv_mean", 25.13, round(float(closed2p["ltv_months"].mean()),2), "closed2p.ltv_months.mean()", tol=0.01)

# conversion rate = mean of per-row (closed/num_leads) ratio -- confirmed as the matching formula
c1_conv_mean = float((closed1["closed"]/closed1["num_leads"]).mean()*100)
c2_conv_mean = float((closed2p["closed"]/closed2p["num_leads"]).mean()*100)
check("closed1_conversion_pct", 5.01, round(c1_conv_mean,2), "mean(closed/num_leads)*100 per row, on closed1", tol=0.05)
check("closed2p_conversion_pct", 7.32, round(c2_conv_mean,2), "mean(closed/num_leads)*100 per row, on closed2p", tol=0.05)

corr_pur = float(pur["closed"].corr(pur["calls_to_closed"]))
check("corr_closed_calls", -0.238, round(corr_pur,3), "pur.closed.corr(pur.calls_to_closed)  # within purchased==1 population", tol=0.002)

# ---- KNOWN DISCREPANCY: closed2p budget/leads "median" in SPEC ----
# Row-level (unweighted) median -- what the SPEC caveat says the comparison unit is:
c2_budget_median_rowlevel = float(closed2p["ad_budget"].median())
c2_leads_median_rowlevel = float(closed2p["num_leads"].median())
check("closed2p_budget_median_ROWLEVEL", 5000, c2_budget_median_rowlevel,
      "closed2p.ad_budget.median()  -- row-level, matches SPEC caveat's stated unit of comparison")
check("closed2p_leads_median_ROWLEVEL", 52.5, c2_leads_median_rowlevel,
      "closed2p.num_leads.median()  -- row-level, matches SPEC caveat's stated unit of comparison")

def _weighted_median(vals, weights):
    d = pd.DataFrame({"v": vals, "w": weights}).sort_values("v").reset_index(drop=True)
    cum = d["w"].cumsum(); total = d["w"].sum(); cutoff = total/2.0
    idx = cum[cum>=cutoff].index[0]
    if abs(cum[idx]-cutoff) < 1e-9 and idx+1 < len(d):
        return (d["v"][idx] + d["v"][idx+1])/2.0
    return float(d["v"][idx])
c2_budget_median_weighted = _weighted_median(closed2p["ad_budget"].values, closed2p["closed"].values)
c2_leads_median_weighted = _weighted_median(closed2p["num_leads"].values, closed2p["closed"].values)
R["closed2p_budget_median_WEIGHTED_BY_DEALS"] = {"expected": 5000, "measured": c2_budget_median_weighted,
    "pass": c2_budget_median_weighted==5000,
    "expr": "weighted median of ad_budget, weight=closed (i.e. counting each closed deal, not each row) -- reproduces SPEC's 5,000 but CONTRADICTS the SPEC caveat that the comparison is row-level, not deal-level"}
R["closed2p_leads_median_WEIGHTED_BY_DEALS"] = {"expected": 52.5, "measured": c2_leads_median_weighted,
    "pass": abs(c2_leads_median_weighted-52.5)<=0.5,
    "expr": "weighted median of num_leads, weight=closed -- close to SPEC's 52.5 but same contradiction as above"}

def tier(b):
    if b <= 1500: return "Low"
    if b <= 5000: return "Mid"
    return "High"
df["_tier"] = df["ad_budget"].apply(tier)
tier_conv = {}
for t in ["Low","Mid","High"]:
    sub = df[df["_tier"]==t]
    tier_conv[t] = float((sub["closed"]/sub["num_leads"]).mean()*100)
check("tier_conv_low", 4.52, round(tier_conv["Low"],2), "mean(closed/num_leads)*100 per row, Low tier", tol=0.02)
check("tier_conv_mid", 8.22, round(tier_conv["Mid"],2), "mean(closed/num_leads)*100 per row, Mid tier", tol=0.02)
check("tier_conv_high", 5.43, round(tier_conv["High"],2), "mean(closed/num_leads)*100 per row, High tier", tol=0.02)

cac_corr = float(df["customer_acquisition_cost"].corr(df["ad_budget"]))
check("cac_ad_budget_corr", 0.83, round(cac_corr,2), "df.customer_acquisition_cost.corr(df.ad_budget)", tol=0.01)

check("leads_not_answered_identity_exact", True,
      bool((df["leads_not_answered"] == df["num_leads"] - df["leads_answered"]).all()),
      "(leads_not_answered == num_leads - leads_answered).all()")

dup_mask_all = df.duplicated(keep=False)
dup_total_rows = int(dup_mask_all.sum())
dup_groups = df[dup_mask_all].drop_duplicates().shape[0]
dup_excess = int(df.duplicated(keep="first").sum())
check("duplicate_total_rows", 19, dup_total_rows, "df.duplicated(keep=False).sum()")
check("duplicate_groups", 9, dup_groups, "df[dup_mask].drop_duplicates().shape[0]")
check("duplicate_excess_rows", 10, dup_excess, 'df.duplicated(keep="first").sum()')
dup_budgets = sorted(df[dup_mask_all]["ad_budget"].unique().tolist())
check("duplicate_budgets", [500,800,1500], dup_budgets, "sorted(df[dup_mask].ad_budget.unique())")
check("duplicate_all_purchased0", True, bool((df[dup_mask_all]["purchased"]==0).all()), "(df[dup_mask].purchased==0).all()")
check("duplicate_closed1_count", 2, int((df[dup_mask_all]["closed"]==1).sum()), "(df[dup_mask].closed==1).sum()")

super_mask = (df["purchased"]==1) & (df["referred"]=="Yes") & (df["upsell"]==1) & (df["ltv_months"]>=34)
super_df = df[super_mask]
check("super_customer_count", 529, int(super_mask.sum()), "purchased==1 & referred==Yes & upsell==1 & ltv_months>=34")
check("super_customer_pct_of_purchased", 16.72, round(float(super_mask.sum()/n_pur*100),2), "count/len(purchased1)*100", tol=0.01)
super_missing_cp = int(super_df["cumulative_profit"].isna().sum())
check("super_customer_missing_cp", 5, super_missing_cp, "super_df.cumulative_profit.isna().sum()")

profit_super = float(super_df["cumulative_profit"].sum())
profit_all_pur = float(pur["cumulative_profit"].sum())
check("super_customer_profit_pct", 33.61, round(profit_super/profit_all_pur*100,2), "sum(profit|super)/sum(profit|purchased1)*100", tol=0.05)

cac_super = float(super_df["customer_acquisition_cost"].mean())
cac_all_pur = float(pur["customer_acquisition_cost"].mean())
check("super_customer_cac_mean", 990.71, round(cac_super,2), "super_df.customer_acquisition_cost.mean()", tol=0.5)
check("all_purchased_cac_mean", 1437.46, round(cac_all_pur,2), "pur.customer_acquisition_cost.mean()", tol=0.5)
cac_diff_pct = (1 - cac_super/cac_all_pur)*100
check("super_customer_cac_cheaper_pct", 31.1, round(cac_diff_pct,1), "(1-cac_super/cac_all)*100", tol=0.2)

# stability across thresholds (median/quartile/decile) for LTV cutoff instead of fixed 34
ltv_pur = pur["ltv_months"]
thresholds = {"median": ltv_pur.median(), "quartile_top(Q3)": ltv_pur.quantile(0.75), "decile_top(D9)": ltv_pur.quantile(0.9)}
stability = {}
for label, thr in thresholds.items():
    m = (pur["referred"]=="Yes") & (pur["upsell"]==1) & (pur["ltv_months"]>=thr)
    seg = pur[m]
    if len(seg)>0 and seg["customer_acquisition_cost"].notna().any():
        cac_seg = float(seg["customer_acquisition_cost"].mean())
        stability[label] = {"threshold": float(thr), "n": int(len(seg)), "cac_mean": round(cac_seg,2),
                             "cheaper_pct_vs_all_purchased": round((1-cac_seg/cac_all_pur)*100,1)}
R["super_customer_cac_stability_across_thresholds"] = {"expected": "CAC advantage holds at every threshold (qualitative)",
    "measured": stability, "pass": all(v["cac_mean"] < cac_all_pur for v in stability.values()),
    "expr": "CAC mean for (referred==Yes & upsell==1 & ltv>=threshold) at median/Q3/D9 of purchased population, vs all-purchased CAC mean"}

upsell_rate_pur = float(pur["upsell"].mean()*100)
majority_baseline = float((pur["upsell"]==0).mean()*100)
referred_rate_pur = float((pur["referred"]=="Yes").mean()*100)
check("upsell_rate_purchased1_pct", 46.35, round(upsell_rate_pur,2), "pur.upsell.mean()*100", tol=0.02)
check("majority_baseline_pct", 53.65, round(majority_baseline,2), "(pur.upsell==0).mean()*100", tol=0.02)
check("referred_yes_rate_purchased1_pct", 42.71, round(referred_rate_pur,2), '(pur.referred=="Yes").mean()*100', tol=0.02)
check("upsell_count_purchased1", 1466, int((pur["upsell"]==1).sum()), "(pur.upsell==1).sum()")
check("majority_baseline_count", 1697, int((pur["upsell"]==0).sum()), "(pur.upsell==0).sum()")

check("purchased_nunique_after_filter", 1, int(pur["purchased"].nunique()), "pur.purchased.nunique()")

anomaly1 = int(((df["closed"]>0) & (df["purchased"]==0)).sum())
anomaly2 = int(((df["purchased"]==0) & (df["ltv_months"]>0)).sum())
check("anomaly_closed_gt0_purchased0", 155, anomaly1, "((closed>0)&(purchased==0)).sum()")
check("anomaly_purchased0_ltv_gt0", 333, anomaly2, "((purchased==0)&(ltv_months>0)).sum()")

out["results"] = R
n_pass = sum(1 for v in R.values() if v["pass"])
n_total = len(R)
out["summary"] = {"pass": n_pass, "total": n_total, "fail": n_total-n_pass}

print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
