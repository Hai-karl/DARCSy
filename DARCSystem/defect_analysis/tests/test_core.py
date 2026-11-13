import pandas as pd
import pytest

from defect_analysis import *
from defect_analysis.analytics import western_electric_run_rule


@pytest.fixture(scope="module")
def df():
    return prepare_records(generate_sample_records())


def test_validation_catches_bad_rows():
    bad = pd.DataFrame([dict(inspection_date="2026-01-01", production_line="A",
        product_type="X", shift="Morning", machine_id="M-01",
        defect_type="Scratch", batch_number="B1", severity="Minor",
        units_inspected=10, defect_count=20)])
    with pytest.raises(ValidationError):
        prepare_records(bad)


def test_trend_rate_is_weighted(df):
    t = defect_rate_trend(df, freq="MS")
    first = t.iloc[0]
    assert first.defect_rate == pytest.approx(first.defect_count / first.units_inspected)


def test_pareto_sorted_and_cumulative(df):
    p = pareto_analysis(df)
    assert p["defect_count"].is_monotonic_decreasing
    assert p["cumulative_pct"].iloc[-1] == pytest.approx(100)
    assert p["vital_few"].iloc[0]


def test_correlation_finds_humidity_or_age(df):
    c = correlation_analysis(df)
    assert {"temperature", "humidity", "machine_age_months"} <= set(c.factor)


def test_p_chart_limits(df):
    ch = p_chart(df, freq="W")
    assert (ch.lcl >= 0).all() and (ch.ucl > ch.center_line).all()
    assert len(western_electric_run_rule(ch)) == len(ch)


def test_rising_trend_detected(df):
    assert trend_direction(defect_rate_trend(df, freq="W"))["direction"] == "increasing"


def test_model_trains_and_suggests(df):
    m = RootCauseClassifier()
    metrics = m.train(df)
    assert metrics["accuracy"] > 0.5  # well above 5-class chance
    out = m.predict_root_causes(df.head(5))
    assert {"suggestion_1", "confidence_1"} <= set(out.columns)
    assert out["confidence_1"].between(0, 1).all()


def test_rbac():
    assert has_permission("QC Engineer", "record:create")
    assert not has_permission("Line Supervisor", "record:create")
    assert not has_permission("IT Administrator", "dashboard:view")
    with pytest.raises(PermissionDenied):
        dashboard_summary(pd.DataFrame(), role="IT Administrator")


def test_dashboard_summary_role_ok(df):
    s = dashboard_summary(df, role="Quality Manager", production_line="Line B")
    assert 0 < s["overall_defect_rate"] < 1


def test_severity_and_batch_rules():
    base = dict(inspection_date="2026-01-01", production_line="A", product_type="X",
                shift="Morning", machine_id="M-01", batch_number="B1", units_inspected=10)
    no_sev = pd.DataFrame([{**base, "defect_type": "Scratch", "defect_count": 2, "severity": "None"}])
    assert any("severity" in p for p in validate_records(no_sev))
    clean_sev = pd.DataFrame([{**base, "defect_type": "None", "defect_count": 0, "severity": "Major"}])
    assert any("severity" in p for p in validate_records(clean_sev))
    blank = pd.DataFrame([{**base, "batch_number": " ", "defect_type": "Scratch", "defect_count": 2, "severity": "Minor"}])
    assert any("batch" in p for p in validate_records(blank))
    ok = pd.DataFrame([{**base, "defect_type": "Scratch", "defect_count": 2, "severity": "Critical"}])
    assert validate_records(ok) == []
