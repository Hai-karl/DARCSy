"""Train, compare and save the defect prediction models.

    python -m defect_analysis.train_model                      # all three targets
    python -m defect_analysis.train_model --targets severity   # one target
    python -m defect_analysis.train_model --data data/defects_data.csv --out models

For each target the script holds out 20 % of the rows (stratified for classification),
compares a baseline with Random Forest and Gradient Boosting using 5-fold cross-validation
on the training part, evaluates the winner on the held-out part, then refits it on all rows
and saves it to <out>/<target>.joblib together with its metadata.
"""
import argparse
import json
import os
from datetime import datetime, timezone

import joblib
import numpy as np
import sklearn
from sklearn.base import clone
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import (GradientBoostingClassifier, GradientBoostingRegressor,
                              RandomForestClassifier, RandomForestRegressor)
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, mean_absolute_error,
                             precision_score, r2_score, recall_score, root_mean_squared_error)
from sklearn.model_selection import StratifiedKFold, KFold, cross_val_score, train_test_split

from .preprocess import (TARGETS, build_pipeline, file_sha256, input_columns, load_dataset,
                         schema_from_data)

BASELINE = "Baseline"
ACC_MARGIN, MAE_MARGIN, R2_MIN = 0.03, 0.05, 0.05    # what counts as "better than guessing"


def _candidates(task, n_estimators, seed):
    if task == "classification":
        return {BASELINE: DummyClassifier(strategy="most_frequent"),
                "Random Forest": RandomForestClassifier(n_estimators=n_estimators, random_state=seed, n_jobs=-1),
                "Gradient Boosting": GradientBoostingClassifier(random_state=seed)}
    return {BASELINE: DummyRegressor(),
            "Random Forest": RandomForestRegressor(n_estimators=n_estimators, random_state=seed, n_jobs=-1),
            "Gradient Boosting": GradientBoostingRegressor(random_state=seed)}


def _metrics(task, y_true, y_pred, labels=None):
    if task == "classification":
        kw = dict(average="weighted", zero_division=0)
        return {"accuracy": accuracy_score(y_true, y_pred), "precision": precision_score(y_true, y_pred, **kw),
                "recall": recall_score(y_true, y_pred, **kw), "f1": f1_score(y_true, y_pred, **kw),
                "f1_macro": f1_score(y_true, y_pred, average="macro", zero_division=0),
                "labels": list(labels), "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist()}
    return {"mae": mean_absolute_error(y_true, y_pred), "rmse": root_mean_squared_error(y_true, y_pred),
            "r2": r2_score(y_true, y_pred)}


def train_target(df, target, cv_folds=5, n_estimators=200, seed=42):
    """Returns {"pipeline": fitted Pipeline, "meta": dict} for one target."""
    task = TARGETS[target]["task"]
    X, y = df[input_columns(target)], df[target]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=seed,
                                              stratify=y if task == "classification" else None)
    cv = (StratifiedKFold if task == "classification" else KFold)(cv_folds, shuffle=True, random_state=seed)
    scoring = "accuracy" if task == "classification" else "neg_mean_absolute_error"
    labels = sorted(y.unique()) if task == "classification" else None

    results, fitted = [], {}
    for name, est in _candidates(task, n_estimators, seed).items():
        pipe = build_pipeline(target, est)
        cv_score = float(cross_val_score(pipe, X_tr, y_tr, cv=cv, scoring=scoring).mean())
        fitted[name] = pipe.fit(X_tr, y_tr)
        results.append({"model": name, "cv_score": cv_score if task == "classification" else -cv_score,
                        "test": _metrics(task, y_te, fitted[name].predict(X_te), labels)})
    real = [r for r in results if r["model"] != BASELINE]
    pick = (max if task == "classification" else min)(real, key=lambda r: r["cv_score"])     # chosen on CV, not on test
    base = next(r for r in results if r["model"] == BASELINE)
    if task == "classification":
        beats = (pick["test"]["accuracy"] >= base["test"]["accuracy"] + ACC_MARGIN
                 and pick["cv_score"] >= base["cv_score"] + ACC_MARGIN)
    else:
        beats = pick["test"]["mae"] <= base["test"]["mae"] * (1 - MAE_MARGIN) and pick["test"]["r2"] >= R2_MIN

    final = build_pipeline(target, clone(_candidates(task, n_estimators, seed)[pick["model"]])).fit(X, y)
    meta = {"target": target, "task": task, "label": TARGETS[target]["label"], "inputs": input_columns(target),
            "selected_model": pick["model"], "beats_baseline": bool(beats), "metrics": pick["test"],
            "baseline_metrics": base["test"], "comparison": results, "cv_folds": cv_folds,
            "n_rows": int(len(df)), "n_train": int(len(X_tr)), "n_test": int(len(X_te)),
            "note": "Metrics are from the 20% held-out rows. The saved model is refit on all rows.",
            "sklearn_version": sklearn.__version__, "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    return {"pipeline": final, "meta": meta}


def train_all(data_path, out_dir="models", targets=None, cv_folds=5, n_estimators=200, seed=42):
    df = load_dataset(data_path)
    schema, sha = schema_from_data(df), file_sha256(data_path)
    os.makedirs(out_dir, exist_ok=True)
    reports = []
    for t in targets or list(TARGETS):
        bundle = train_target(df, t, cv_folds, n_estimators, seed)
        bundle["meta"].update(schema=schema, data_sha256=sha, data_file=os.path.basename(data_path))
        joblib.dump(bundle, os.path.join(out_dir, f"{t}.joblib"))
        reports.append(bundle["meta"])
    with open(os.path.join(out_dir, "training_report.json"), "w") as f:
        json.dump(reports, f, indent=2, default=lambda o: o.item() if isinstance(o, np.generic) else str(o))
    return reports


def _line(m):
    t = m["metrics"]
    if m["task"] == "classification":
        b = m["baseline_metrics"]
        return (f"{m['label']:<12} {m['selected_model']:<18} accuracy {t['accuracy']:.3f} (guessing {b['accuracy']:.3f})  "
                f"precision {t['precision']:.3f}  recall {t['recall']:.3f}  F1 {t['f1']:.3f}")
    b = m["baseline_metrics"]
    return (f"{m['label']:<12} {m['selected_model']:<18} MAE {t['mae']:.2f} (guessing {b['mae']:.2f})  "
            f"RMSE {t['rmse']:.2f}  R2 {t['r2']:.3f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data/defects_data.csv")
    ap.add_argument("--out", default="models")
    ap.add_argument("--targets", nargs="+", choices=list(TARGETS), default=None)
    ap.add_argument("--cv-folds", type=int, default=5)
    ap.add_argument("--trees", type=int, default=200)
    a = ap.parse_args()
    for m in train_all(a.data, a.out, a.targets, a.cv_folds, a.trees):
        print(_line(m))
        print(f"{'':<12} better than guessing: {'YES' if m['beats_baseline'] else 'NO'}")
        if m["task"] == "classification":
            print(f"{'':<12} confusion matrix {m['metrics']['labels']}: {m['metrics']['confusion_matrix']}")
    print(f"Saved to {a.out}/")


if __name__ == "__main__":
    main()
