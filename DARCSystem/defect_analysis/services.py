"""Service layer: RBAC-protected entry points the Flask routes will call.

Each function maps to one API endpoint in FYP2, e.g.
    @app.get("/api/dashboard")  ->  dashboard_summary(df, role=session_role)
"""
import pandas as pd

from .analytics import (correlation_analysis, defect_rate_trend, p_chart,
                        pareto_analysis, trend_direction)
from .data_management import filter_records, prepare_records
from .rbac import require_permission
from .root_cause import RootCauseClassifier


@require_permission("record:create")
def add_records(existing: pd.DataFrame, new_rows: pd.DataFrame) -> pd.DataFrame:
    """Validate and append new inspector-entered records."""
    new_prepared = prepare_records(new_rows)          # raises ValidationError if bad
    return pd.concat([existing, new_prepared], ignore_index=True).sort_values(
        "inspection_date").reset_index(drop=True)


@require_permission("dashboard:view")
def dashboard_summary(df: pd.DataFrame, freq: str = "W", **filters) -> dict:
    """Everything the dashboard needs in one call (Chart.js-ready tables)."""
    data = filter_records(df, **filters)
    trend = defect_rate_trend(data, freq=freq)
    return {
        "overall_defect_rate": float(data["defect_count"].sum() / data["units_inspected"].sum()),
        "trend": trend,
        "trend_direction": trend_direction(trend),
        "pareto_defect_type": pareto_analysis(data, by="defect_type"),
        "pareto_machine": pareto_analysis(data, by="machine_id"),
        "correlations": correlation_analysis(data),
        "control_chart": p_chart(data, freq=freq),
    }


@require_permission("rootcause:train")
def train_root_cause_model(df: pd.DataFrame) -> RootCauseClassifier:
    model = RootCauseClassifier()
    model.train(df)
    return model


@require_permission("rootcause:predict")
def suggest_root_causes(model: RootCauseClassifier, records: pd.DataFrame, top_k: int = 3):
    return model.predict_root_causes(records, top_k=top_k)
