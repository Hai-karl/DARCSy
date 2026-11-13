"""Statistical analysis functions: defect-rate trend, Pareto analysis,
Pearson correlation and p-type control charts."""
import numpy as np
import pandas as pd
from scipy import stats

from .config import (CONTROL_CHART_SIGMA, NO_DEFECT_LABEL, NUMERIC_FACTORS,
                     PARETO_CUTOFF)


# ---------------------------------------------------------------- trend ----
def defect_rate_trend(df: pd.DataFrame, freq: str = "W", group_by: str = None,
                      window: int = 4) -> pd.DataFrame:
    """Aggregate defect rate over time.

    freq: pandas offset alias ('D' daily, 'W' weekly, 'MS' monthly).
    group_by: optional column (e.g. 'production_line') for one series per group.
    window: moving-average window (in periods).
    Rate is total defects / total units (not a mean of row rates).
    """
    keys = [pd.Grouper(key="inspection_date", freq=freq)]
    if group_by:
        keys.append(group_by)
    agg = (df.groupby(keys)[["units_inspected", "defect_count"]].sum()
             .reset_index())
    agg = agg[agg["units_inspected"] > 0].copy()
    agg["defect_rate"] = agg["defect_count"] / agg["units_inspected"]

    if group_by:
        agg["moving_avg"] = (agg.groupby(group_by)["defect_rate"]
                               .transform(lambda s: s.rolling(window, min_periods=1).mean()))
    else:
        agg["moving_avg"] = agg["defect_rate"].rolling(window, min_periods=1).mean()
    return agg


def trend_direction(trend_df: pd.DataFrame, alpha: float = 0.05) -> dict:
    """Linear-regression slope of defect_rate over period index.

    Returns slope per period, p-value and a label: increasing / decreasing / stable.
    """
    y = trend_df["defect_rate"].to_numpy()
    if len(y) < 3:
        return {"slope": np.nan, "p_value": np.nan, "direction": "insufficient data"}
    res = stats.linregress(np.arange(len(y)), y)
    if res.pvalue < alpha:
        direction = "increasing" if res.slope > 0 else "decreasing"
    else:
        direction = "stable"
    return {"slope": float(res.slope), "p_value": float(res.pvalue),
            "direction": direction}


# --------------------------------------------------------------- Pareto ----
def pareto_analysis(df: pd.DataFrame, by: str = "defect_type",
                    cutoff: float = PARETO_CUTOFF) -> pd.DataFrame:
    """Rank categories by defect count with cumulative percentage.

    `vital_few` is True for categories needed to reach the cutoff
    (default 80 %). Rows with no defects are excluded.
    """
    data = df[df["defect_count"] > 0]
    if by == "defect_type":
        data = data[data["defect_type"] != NO_DEFECT_LABEL]
    counts = (data.groupby(by)["defect_count"].sum()
                  .sort_values(ascending=False).reset_index())
    total = counts["defect_count"].sum()
    if total == 0:
        return counts.assign(percentage=0.0, cumulative_pct=0.0, vital_few=False)
    counts["percentage"] = counts["defect_count"] / total * 100
    counts["cumulative_pct"] = counts["percentage"].cumsum()
    before = counts["cumulative_pct"] - counts["percentage"]
    counts["vital_few"] = before < cutoff * 100   # includes the item crossing the cutoff
    return counts


# ------------------------------------------------------------- Pearson ----
def correlation_analysis(df: pd.DataFrame, factors=None,
                         alpha: float = 0.05) -> pd.DataFrame:
    """Pearson correlation between each numeric factor and defect_rate."""
    factors = factors or NUMERIC_FACTORS
    rows = []
    for f in factors:
        if f not in df.columns:
            continue
        pair = pd.DataFrame({"x": pd.to_numeric(df[f], errors="coerce"),
                             "y": df["defect_rate"]}).dropna()
        if len(pair) < 3 or pair["x"].nunique() < 2:
            continue
        r, p = stats.pearsonr(pair["x"], pair["y"])
        rows.append({"factor": f, "r": r, "p_value": p, "n": len(pair),
                     "significant": p < alpha, "strength": _strength(r)})
    cols = ["factor", "r", "p_value", "n", "significant", "strength"]
    out = pd.DataFrame(rows, columns=cols)
    if out.empty:
        return out
    return out.reindex(out["r"].abs().sort_values(ascending=False).index).reset_index(drop=True)


def _strength(r: float) -> str:
    a = abs(r)
    label = ("negligible" if a < 0.1 else "weak" if a < 0.3
             else "moderate" if a < 0.5 else "strong")
    sign = "positive" if r > 0 else "negative"
    return label if label == "negligible" else f"{label} {sign}"


# -------------------------------------------------------- control chart ----
def p_chart(df: pd.DataFrame, freq: str = "W",
            sigma: float = CONTROL_CHART_SIGMA, baseline_periods: int = None) -> pd.DataFrame:
    """p-chart (proportion defective) with variable-sample-size limits.

    UCL/LCL = p_bar +/- sigma * sqrt(p_bar * (1 - p_bar) / n_i), LCL floored at 0.
    baseline_periods: if given, p_bar is computed from the first N periods only
    (useful for a known-stable baseline).
    Adds `out_of_control` flag (point beyond limits).
    """
    agg = (df.groupby(pd.Grouper(key="inspection_date", freq=freq))
             [["units_inspected", "defect_count"]].sum().reset_index())
    agg = agg[agg["units_inspected"] > 0].reset_index(drop=True)
    agg["defect_rate"] = agg["defect_count"] / agg["units_inspected"]

    base = agg.head(baseline_periods) if baseline_periods else agg
    p_bar = base["defect_count"].sum() / base["units_inspected"].sum()

    se = np.sqrt(p_bar * (1 - p_bar) / agg["units_inspected"])
    agg["center_line"] = p_bar
    agg["ucl"] = p_bar + sigma * se
    agg["lcl"] = (p_bar - sigma * se).clip(lower=0)
    agg["out_of_control"] = (agg["defect_rate"] > agg["ucl"]) | (agg["defect_rate"] < agg["lcl"])
    return agg


def western_electric_run_rule(chart: pd.DataFrame, run_length: int = 8) -> pd.Series:
    """Flag points that complete a run of `run_length` consecutive points on
    the same side of the centre line (a common shift signal)."""
    side = np.sign(chart["defect_rate"] - chart["center_line"])
    flags = np.zeros(len(chart), dtype=bool)
    streak, prev = 0, 0
    for i, s in enumerate(side):
        streak = streak + 1 if (s == prev and s != 0) else (1 if s != 0 else 0)
        prev = s
        if streak >= run_length:
            flags[i] = True
    return pd.Series(flags, index=chart.index, name="run_rule_signal")


# ------------------------------------------------------ correlation matrix ----
def correlation_matrix(df: pd.DataFrame, top_machines: int = 4) -> dict:
    """Pearson matrix for the dashboard heatmap: defect rate, process factors,
    high severity, shifts, lines and the busiest machines."""
    X = pd.DataFrame({"Defect rate": df["defect_rate"].astype(float)})
    for col, lbl in [("temperature", "Temperature"), ("humidity", "Humidity"),
                     ("machine_age_months", "Machine age")]:
        if col in df.columns and pd.to_numeric(df[col], errors="coerce").notna().any():
            X[lbl] = pd.to_numeric(df[col], errors="coerce")
    X["High severity"] = df["severity"].isin(["Major", "Critical", "Safety-Critical"]).astype(float)
    for v in sorted(df["shift"].unique()):
        X[f"{v} shift"] = (df["shift"] == v).astype(float)
    for v in sorted(df["production_line"].unique()):
        X[v] = (df["production_line"] == v).astype(float)
    for m in df.groupby("machine_id")["defect_count"].sum().nlargest(top_machines).index:
        X[f"Machine {m}"] = (df["machine_id"] == m).astype(float)
    corr = X.loc[:, X.nunique() > 1].corr().fillna(0).round(2)
    return {"labels": list(corr.columns), "matrix": corr.values.tolist()}


# -------------------------------------------------- corrective-action effect ----
def corrective_action_effectiveness(df, line, machine, defect_type, implemented,
                                    window_days: int = 28) -> dict:
    """Defect rate in the window before vs after the action was implemented."""
    imp, w = pd.Timestamp(implemented), pd.Timedelta(days=window_days)
    d = df[df["production_line"] == line]
    if machine:
        d = d[d["machine_id"] == machine]

    def rate(lo, hi):
        x = d[(d["inspection_date"] >= lo) & (d["inspection_date"] < hi)]
        units = int(x["units_inspected"].sum())
        if defect_type:
            x = x[x["defect_type"] == defect_type]
        return (x["defect_count"].sum() / units if units else None), units

    before, bu = rate(imp - w, imp)
    after, au = rate(imp, imp + w)
    out = {"before_rate": before, "after_rate": after, "before_units": bu,
           "after_units": au, "window_days": window_days}
    covered = len(df) and df["inspection_date"].max() >= imp + w - pd.Timedelta(days=1)
    if before in (None, 0) or after is None or not covered:
        return {**out, "status": "insufficient data", "change_pct": None,
                "message": f"Not enough data yet: needs {window_days} days of records before and after "
                           f"the action, with a non-zero baseline."}
    change = (after - before) / before * 100
    status = "improved" if change <= -5 else "worse" if change >= 5 else "no clear change"
    return {**out, "status": status, "change_pct": round(change, 1),
            "message": f"Defect rate went from {before:.2%} to {after:.2%} ({change:+.1f}%) "
                       f"in the {window_days} days after the action: {status}."}


# ------------------------------------------------ investigate a chart period ----
def period_bounds(ts, freq: str):
    """First and last day covered by a trend bucket (D, W = week ending Sunday, MS)."""
    ts = pd.Timestamp(ts)
    if freq == "D":
        return ts, ts
    if freq == "W":
        return ts - pd.Timedelta(days=6), ts
    return ts, ts + pd.offsets.MonthEnd(0)


def what_changed(df: pd.DataFrame, start, end, baseline_multiple: int = 4,
                 min_units: int = 100, top: int = 6) -> dict:
    """Compare one period with the periods just before it and rank what moved.

    For each machine, shift, product, line, defect type and severity the extra defects
    are (rate now - rate before) x units now: the defects that would not have happened
    at the earlier rate. Only increases are returned.
    """
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    span = (end - start) + pd.Timedelta(days=1)
    cur = df[(df["inspection_date"] >= start) & (df["inspection_date"] <= end)]
    base = df[(df["inspection_date"] >= start - span * baseline_multiple) & (df["inspection_date"] < start)]
    cu, cd = int(cur["units_inspected"].sum()), int(cur["defect_count"].sum())
    bu, bd = int(base["units_inspected"].sum()), int(base["defect_count"].sum())
    out = {"start": str(start.date()), "end": str(end.date()),
           "period": {"units": cu, "defects": cd, "rate": cd / cu if cu else None},
           "baseline": {"units": bu, "defects": bd, "rate": bd / bu if bu else None,
                        "days": int(span.days * baseline_multiple)},
           "drivers": []}
    if not cu or not bu:
        return {**out, "message": "Not enough earlier data to compare this period."}
    drivers = []
    for col, label in [("machine_id", "Machine"), ("shift", "Shift"), ("product_type", "Product"),
                       ("production_line", "Line")]:
        for v, g in cur.groupby(col):
            gb = base[base[col] == v]
            u, ub = g["units_inspected"].sum(), gb["units_inspected"].sum()
            if u < min_units or ub < min_units:
                continue
            now, before = g["defect_count"].sum() / u, gb["defect_count"].sum() / ub
            drivers.append((label, v, now, before, (now - before) * u, int(g["defect_count"].sum())))
    for col, label in [("defect_type", "Defect type"), ("severity", "Severity")]:
        for v, g in cur[cur[col] != NO_DEFECT_LABEL].groupby(col):
            now = g["defect_count"].sum() / cu
            before = base[base[col] == v]["defect_count"].sum() / bu
            drivers.append((label, v, now, before, (now - before) * cu, int(g["defect_count"].sum())))
    ranked = sorted((d for d in drivers if d[4] >= 0.5), key=lambda d: -d[4])[:top]
    out["drivers"] = [{"dimension": a, "value": str(b), "rate_now": float(c), "rate_before": float(d),
                       "extra_defects": round(float(e), 1), "defects_now": f} for a, b, c, d, e, f in ranked]
    if not out["drivers"]:
        out["message"] = "No single machine, shift or defect type stands out. The change looks spread out."
    return out


def similar_periods(df: pd.DataFrame, start, end, freq: str = "W", line: str = None,
                    top: int = 5, min_defects: int = 10) -> list:
    """Other periods (per production line) whose mix of defect types, machines and
    shifts looks like the selected period. Cosine similarity of the three mixes."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    d = df[(df["defect_count"] > 0) & (df["defect_type"] != NO_DEFECT_LABEL)]
    dims = ["defect_type", "machine_id", "shift"]
    levels = {k: sorted(d[k].unique()) for k in dims}

    def vec(x):
        parts = []
        for k in dims:
            s = x.groupby(k)["defect_count"].sum().reindex(levels[k], fill_value=0).astype(float)
            parts.append(s.values / s.sum() if s.sum() else s.values)
        return np.concatenate(parts)

    tgt = d[(d["inspection_date"] >= start) & (d["inspection_date"] <= end)]
    if line:
        tgt = tgt[tgt["production_line"] == line]
    if d.empty or tgt["defect_count"].sum() < min_defects:
        return []
    tv = vec(tgt)
    totals = df.groupby([pd.Grouper(key="inspection_date", freq=freq), "production_line"])[
        ["units_inspected", "defect_count"]].sum()
    out = []
    for (per, ln), g in d.groupby([pd.Grouper(key="inspection_date", freq=freq), "production_line"]):
        if g["defect_count"].sum() < min_defects:
            continue
        ps, pe = period_bounds(per, freq)
        if ps <= end and pe >= start and (not line or ln == line):
            continue                                   # the selected period itself
        gv = vec(g)
        denom = np.linalg.norm(tv) * np.linalg.norm(gv)
        if not denom:
            continue
        u = totals.loc[(per, ln), "units_inspected"]
        out.append({"start": str(ps.date()), "end": str(pe.date()), "line": ln,
                    "similarity": round(float(tv @ gv / denom), 3),
                    "defect_rate": float(g["defect_count"].sum() / u) if u else None,
                    "defects": int(g["defect_count"].sum()),
                    "main_defect": str(g.groupby("defect_type")["defect_count"].sum().idxmax())})
    return sorted(out, key=lambda r: -r["similarity"])[:top]
