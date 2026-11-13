"""Builds the JSON payload the dashboard front end consumes."""
import pandas as pd

from defect_analysis import correlation_analysis, pareto_analysis
from defect_analysis.analytics import correlation_matrix, period_bounds


def build_bundle(df: pd.DataFrame, model=None) -> dict:
    out = {"weekly": {}, "pareto": {}, "machine": {}, "severity": {}, "trend": {}, "corr": [], "acc": None,
           "imp": [], "pred": [], "lines": []}
    if df.empty:
        return out
    lines = sorted(df.production_line.unique())
    out["lines"] = lines
    for line in ["All"] + lines:
        d = df if line == "All" else df[df.production_line == line]
        w = (d.groupby(pd.Grouper(key="inspection_date", freq="W"))
               [["units_inspected", "defect_count"]].sum().reset_index())
        out["weekly"][line] = [[r.inspection_date.strftime("%d %b"), int(r.units_inspected),
                                int(r.defect_count)] for r in w.itertuples() if r.units_inspected > 0]
        out["pareto"][line] = {r.defect_type: int(r.defect_count) for r in pareto_analysis(d).itertuples()}
        for key, freq, fmt in (("D", "D", "%d %b"), ("W", "W", "%d %b"), ("M", "MS", "%b %Y")):
            g = d.groupby(pd.Grouper(key="inspection_date", freq=freq))[["units_inspected", "defect_count"]].sum().reset_index()
            out["trend"].setdefault(key, {})[line] = [
                [r.inspection_date.strftime(fmt), int(r.units_inspected), int(r.defect_count),
                 *[x.strftime("%Y-%m-%d") for x in period_bounds(r.inspection_date, freq)]]
                for r in g.itertuples() if r.units_inspected > 0]
        out["severity"][line] = {r.severity: int(r.defect_count) for r in pareto_analysis(d, by="severity").itertuples()}
        out["machine"][line] = {r.machine_id: int(r.defect_count)
                                for r in pareto_analysis(d, by="machine_id").itertuples()}
    out["heat"] = correlation_matrix(df)
    c = correlation_analysis(df)
    out["corr"] = [[r.factor, round(float(r.r), 3), bool(r.significant)] for r in c.itertuples()]

    if model is not None and model.pipeline is not None:
        out["acc"] = round(float(model.metrics_["accuracy"]), 3) if model.metrics_ else None
        if model.metrics_:
            m = model.metrics_
            out["metrics"] = {k: m[k] for k in ("precision", "recall", "f1_weighted", "benchmark") if k in m}
        out["imp"] = [[r.feature, round(float(r.importance), 3)]
                      for r in model.feature_importance(6).itertuples()]
        recent = df[df.defect_count > 0].tail(6)
        if len(recent):
            p = model.predict_root_causes(recent)
            for i, r in recent.iterrows():
                out["pred"].append(dict(
                    date=r["inspection_date"].strftime("%d %b"), line=r["production_line"],
                    machine=r["machine_id"], shift=r["shift"], defect=r["defect_type"],
                    s=[[p.loc[i, f"suggestion_{k}"], round(float(p.loc[i, f"confidence_{k}"]), 2)]
                       for k in (1, 2, 3)]))
    return out
