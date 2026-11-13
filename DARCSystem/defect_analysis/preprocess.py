"""Preprocessing for the defects_data.csv prediction module.

One scikit-learn Pipeline holds every preprocessing step (date features, one-hot
encoding, scaling), so training and prediction transform the data identically.
"""
import hashlib

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

DATE_FORMAT = "%m/%d/%Y"                       # as written in defects_data.csv (M/D/YYYY)
ID_COLUMN = "defect_id"                        # never a feature
EXPECTED_COLUMNS = ["defect_id", "product_id", "defect_type", "defect_date", "defect_location",
                    "severity", "inspection_method", "repair_cost"]
CATEGORICAL = ["product_id", "defect_type", "defect_location", "severity", "inspection_method"]
TEXT_CATEGORICAL = ["defect_type", "defect_location", "severity", "inspection_method"]
BASE_INPUTS = ["product_id", "defect_type", "defect_date", "defect_location", "severity", "inspection_method"]

TARGETS = {                                    # what can be predicted
    "severity": {"task": "classification", "label": "Severity"},
    "defect_type": {"task": "classification", "label": "Defect type"},
    "repair_cost": {"task": "regression", "label": "Repair cost"},
}


class SchemaError(ValueError):
    """The CSV does not match the expected schema."""


def input_columns(target: str) -> list:
    """Model inputs for a target. repair_cost is only known after the repair is done,
    so it is never an input; the target itself is excluded too."""
    return [c for c in BASE_INPUTS if c != target]


def file_sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_dataset(path: str) -> pd.DataFrame:
    """Load defects_data.csv and verify schema and data types. Returns the rows
    without defect_id (the date stays a string; the Pipeline parses it)."""
    df = pd.read_csv(path)
    problems = []
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        raise SchemaError(f"Missing columns: {missing}")
    df = df[EXPECTED_COLUMNS].copy()
    if df.isnull().any().any():
        problems.append(f"Missing values: {df.isnull().sum()[lambda s: s > 0].to_dict()}")
    for c in ("defect_id", "product_id"):
        if not pd.api.types.is_integer_dtype(df[c]):
            problems.append(f"{c} must be whole numbers.")
    if not pd.api.types.is_numeric_dtype(df["repair_cost"]):
        problems.append("repair_cost must be numeric.")
    elif (df["repair_cost"] < 0).any():
        problems.append("repair_cost cannot be negative.")
    try:
        pd.to_datetime(df["defect_date"], format=DATE_FORMAT)
    except (ValueError, TypeError):
        problems.append(f"defect_date must be written as M/D/YYYY, e.g. 6/6/2024.")
    if df["defect_id"].duplicated().any():
        problems.append("defect_id must be unique.")
    if problems:
        raise SchemaError(" ".join(problems))
    for c in TEXT_CATEGORICAL:
        df[c] = df[c].astype(str).str.strip()
    return df.drop(columns=[ID_COLUMN]).reset_index(drop=True)


def schema_from_data(df: pd.DataFrame) -> dict:
    """Valid options and ranges, learned from the data (so retraining updates them)."""
    dates = pd.to_datetime(df["defect_date"], format=DATE_FORMAT)
    return {"categories": {c: sorted(df[c].unique().tolist()) for c in TEXT_CATEGORICAL},
            "product_id": {"min": int(df["product_id"].min()), "max": int(df["product_id"].max())},
            "date": {"min": str(dates.min().date()), "max": str(dates.max().date())},
            "repair_cost": {"min": float(df["repair_cost"].min()), "max": float(df["repair_cost"].max())},
            "n_rows": int(len(df))}


class DateFeatures(BaseEstimator, TransformerMixin):
    """Turns a raw date column into month, day_of_week and day_of_year."""
    names = ["month", "day_of_week", "day_of_year"]

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        s = pd.to_datetime(pd.Series(np.asarray(X).ravel()), format="mixed")
        return np.column_stack([s.dt.month, s.dt.dayofweek, s.dt.dayofyear]).astype(float)

    def get_feature_names_out(self, input_features=None):
        return np.array(self.names)


def build_pipeline(target: str, estimator) -> Pipeline:
    cols = input_columns(target)
    pre = ColumnTransformer([
        ("categorical", OneHotEncoder(handle_unknown="ignore"), [c for c in CATEGORICAL if c in cols]),
        ("date", Pipeline([("features", DateFeatures()), ("scale", StandardScaler())]), ["defect_date"]),
    ])
    return Pipeline([("preprocess", pre), ("model", estimator)])
