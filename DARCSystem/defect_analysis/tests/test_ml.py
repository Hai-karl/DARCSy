import os

import numpy as np
import pandas as pd
import pytest

from defect_analysis.predictor import PredictionError, load_bundle, predict, validate_inputs
from defect_analysis.preprocess import (DateFeatures, SchemaError, input_columns, load_dataset,
                                        schema_from_data)
from defect_analysis.train_model import train_all

DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data", "defects_data.csv")
OK = dict(product_id=15, defect_type="Structural", defect_date="6/6/2024", defect_location="Component",
          severity="Minor", inspection_method="Visual Inspection")


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    out = str(tmp_path_factory.mktemp("models"))
    return out, {m["target"]: m for m in train_all(DATA, out, cv_folds=3, n_estimators=15)}


def test_dataset_loads_and_schema_is_learned():
    df = load_dataset(DATA)
    assert len(df) == 1000 and "defect_id" not in df.columns
    s = schema_from_data(df)
    assert s["categories"]["severity"] == ["Critical", "Minor", "Moderate"]
    assert (s["product_id"]["min"], s["product_id"]["max"]) == (1, 100)
    assert (s["date"]["min"], s["date"]["max"]) == ("2024-01-01", "2024-06-30")


@pytest.mark.parametrize("change", [
    lambda d: d.drop(columns=["severity"]),
    lambda d: d.assign(defect_date="2024-06-06"),
    lambda d: d.assign(repair_cost=d["repair_cost"].where(d.index > 0)),
    lambda d: pd.concat([d, d.head(1)]),                       # duplicate defect_id
])
def test_bad_csv_is_rejected(tmp_path, change):
    p = tmp_path / "bad.csv"
    change(pd.read_csv(DATA)).to_csv(p, index=False)
    with pytest.raises(SchemaError):
        load_dataset(str(p))


def test_date_features():
    f = DateFeatures().fit_transform(pd.DataFrame({"d": ["6/6/2024", "2024-12-31"]}))
    assert f.tolist() == [[6, 3, 158], [12, 1, 366]]


def test_training_outputs(trained):
    out, metas = trained
    assert set(metas) == {"severity", "defect_type", "repair_cost"}
    for t, m in metas.items():
        assert os.path.exists(os.path.join(out, f"{t}.joblib"))
        assert "repair_cost" not in m["inputs"] and "defect_id" not in m["inputs"] and t not in m["inputs"]
        assert m["inputs"] == input_columns(t) and m["n_train"] == 800 and m["n_test"] == 200
        assert m["selected_model"] in ("Random Forest", "Gradient Boosting") and isinstance(m["beats_baseline"], bool)
    c = metas["severity"]["metrics"]
    assert {"accuracy", "precision", "recall", "f1"} <= set(c) and np.sum(c["confusion_matrix"]) == 200
    assert {"mae", "rmse", "r2"} <= set(metas["repair_cost"]["metrics"])
    assert metas["severity"]["schema"]["n_rows"] == 1000 and len(metas["severity"]["data_sha256"]) == 64


def test_pipeline_tolerates_unseen_values(trained):
    b = load_bundle(trained[0], "severity")
    X = pd.DataFrame([{**OK, "product_id": 999, "defect_type": "Brand new type", "defect_date": "2024-02-30"[:8] + "29"}])
    assert b["pipeline"].predict(X)[0] in ("Critical", "Minor", "Moderate")


def test_validation_rules(trained):
    schema = load_bundle(trained[0], "severity")["meta"]["schema"]
    inp = {k: v for k, v in OK.items() if k != "severity"}
    assert validate_inputs(schema, "severity", inp).iloc[0]["defect_date"] == "2024-06-06"
    assert validate_inputs(schema, "severity", {**inp, "defect_date": "2024-06-06", "product_id": "15"}).iloc[0]["product_id"] == 15
    bad_cases = [({**inp, "defect_type": "Electrical"}, "defect_type must be one of"),
                 ({**inp, "product_id": 0}, "between 1 and 100"), ({**inp, "product_id": 7.5}, "whole number"),
                 ({**inp, "defect_date": "1/1/2023"}, "between 2024-01-01 and 2024-06-30"),
                 ({**inp, "defect_date": "13/45/2024"}, "valid date"),
                 ({**inp, "repair_cost": 100}, "only known after the repair"),
                 ({**inp, "severity": "Minor"}, "being predicted"), ({**inp, "bogus": 1}, "Unknown field"),
                 ({k: v for k, v in inp.items() if k != "defect_location"}, "defect_location is required")]
    for body, text in bad_cases:
        with pytest.raises(PredictionError) as e:
            validate_inputs(schema, "severity", body)
        assert any(text in p for p in e.value.problems), (body, e.value.problems)
    with pytest.raises(PredictionError):
        validate_inputs(schema, "nonsense", inp)


def test_predictions(trained):
    c = predict(load_bundle(trained[0], "severity"), {k: v for k, v in OK.items() if k != "severity"})
    assert c["prediction"] in c["probabilities"] and abs(sum(c["probabilities"].values()) - 1) < 1e-6
    r = predict(load_bundle(trained[0], "repair_cost"), OK)
    assert 10 <= r["prediction"] <= 1000 and r["likely_range"][0] <= r["prediction"] <= r["likely_range"][1]
    assert "quality" in r and isinstance(r["quality"]["beats_baseline"], bool)
