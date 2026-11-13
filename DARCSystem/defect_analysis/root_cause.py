"""Supervised decision-tree root cause identification.

IMPORTANT: outputs are probabilistic ML *suggestions* ranked by confidence,
not definitive causal determinations. Engineers should verify before acting.
"""
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (accuracy_score, classification_report, confusion_matrix,
                             f1_score, precision_score, recall_score)
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.tree import DecisionTreeClassifier, export_text

from .config import (CATEGORICAL_FEATURES, MIN_TRAINING_ROWS, NO_DEFECT_LABEL,
                     NUMERIC_FACTORS)


class RootCauseClassifier:
    def __init__(self, random_state: int = 42):
        self.random_state = random_state
        self.pipeline = None
        self.cat_features = None
        self.num_features = None
        self.metrics_ = None

    # ------------------------------------------------------------ data ----
    def _select_training_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        data = df[(df["defect_count"] > 0)
                  & (df["defect_type"] != NO_DEFECT_LABEL)
                  & df["root_cause"].notna()]
        if len(data) < MIN_TRAINING_ROWS:
            raise ValueError(f"Need at least {MIN_TRAINING_ROWS} labelled defect "
                             f"records to train; found {len(data)}.")
        return data

    def _resolve_features(self, df):
        self.cat_features = [c for c in CATEGORICAL_FEATURES if c in df.columns]
        self.num_features = [c for c in NUMERIC_FACTORS
                             if c in df.columns
                             and pd.to_numeric(df[c], errors="coerce").notna().any()]

    def _X(self, df):
        X = df.reindex(columns=self.cat_features + self.num_features).copy()
        for c in self.cat_features:          # missing categorical -> unseen category
            X[c] = X[c].astype(object).where(X[c].notna(), "unknown")
        for c in self.num_features:
            X[c] = pd.to_numeric(X[c], errors="coerce")
        return X

    # ----------------------------------------------------------- train ----
    def train(self, df: pd.DataFrame, test_size: float = 0.2, tune: bool = True) -> dict:
        """Train, (optionally) tune depth/leaf size by cross-validation, and
        evaluate on a stratified hold-out set. Returns the metrics dict."""
        data = self._select_training_rows(df)
        self._resolve_features(data)
        X, y = self._X(data), data["root_cause"].astype(str)

        stratify = y if y.value_counts().min() >= 2 else None
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=test_size, random_state=self.random_state, stratify=stratify)

        pre = ColumnTransformer([
            ("cat", OneHotEncoder(handle_unknown="ignore"), self.cat_features),
            ("num", "passthrough", self.num_features),
        ])
        # Decision trees can't take NaN in older sklearn; 1.3+ supports it natively.
        tree = DecisionTreeClassifier(random_state=self.random_state,
                                      class_weight="balanced")
        pipe = Pipeline([("prep", pre), ("tree", tree)])

        if tune:
            grid = {"tree__max_depth": [3, 4, 5, 6, 8, None],
                    "tree__min_samples_leaf": [1, 3, 5, 10]}
            cv = 5 if y_tr.value_counts().min() >= 5 else 3
            search = GridSearchCV(pipe, grid, cv=cv, scoring="f1_weighted", n_jobs=-1)
            search.fit(X_tr, y_tr)
            self.pipeline = search.best_estimator_
            best_params = search.best_params_
        else:
            self.pipeline = pipe.fit(X_tr, y_tr)
            best_params = {}

        pred = self.pipeline.predict(X_te)
        rf = Pipeline([("prep", clone(pre)), ("tree", RandomForestClassifier(
            n_estimators=200, random_state=self.random_state, class_weight="balanced"))]).fit(X_tr, y_tr)
        rf_pred = rf.predict(X_te)
        classes = list(self.pipeline.classes_)
        self.metrics_ = {
            "n_train": len(X_tr), "n_test": len(X_te),
            "accuracy": accuracy_score(y_te, pred),
            "precision": precision_score(y_te, pred, average="weighted", zero_division=0),
            "recall": recall_score(y_te, pred, average="weighted", zero_division=0),
            "f1_weighted": f1_score(y_te, pred, average="weighted"),
            "classes": classes, "confusion": confusion_matrix(y_te, pred, labels=classes).tolist(),
            "benchmark": {"model": "Random Forest",
                          "accuracy": accuracy_score(y_te, rf_pred),
                          "precision": precision_score(y_te, rf_pred, average="weighted", zero_division=0),
                          "recall": recall_score(y_te, rf_pred, average="weighted", zero_division=0),
                          "f1_weighted": f1_score(y_te, rf_pred, average="weighted")},
            "best_params": best_params,
            "report": classification_report(y_te, pred, zero_division=0),
        }
        return self.metrics_

    # --------------------------------------------------------- predict ----
    def _check_trained(self):
        if self.pipeline is None:
            raise RuntimeError("Model is not trained. Call train() first.")

    def predict_root_causes(self, records: pd.DataFrame, top_k: int = 3) -> pd.DataFrame:
        """Return the top-k suggested root causes with probabilities per record."""
        self._check_trained()
        proba = self.pipeline.predict_proba(self._X(records))
        classes = self.pipeline.classes_
        rows = []
        for p in proba:
            order = p.argsort()[::-1][:top_k]
            row = {}
            for rank, idx in enumerate(order, start=1):
                row[f"suggestion_{rank}"] = classes[idx]
                row[f"confidence_{rank}"] = float(p[idx])
            rows.append(row)
        return pd.DataFrame(rows, index=records.index)

    def investigate(self, records: pd.DataFrame, min_records: int = 10, min_conf: float = 0.5) -> dict:
        """Average the model's probabilities over a defect pattern (UC-05)."""
        self._check_trained()
        mean = self.pipeline.predict_proba(self._X(records)).mean(axis=0)
        order = mean.argsort()[::-1]
        ranked = [{"cause": self.pipeline.classes_[i], "confidence": float(mean[i])} for i in order]
        low = len(records) < min_records or ranked[0]["confidence"] < min_conf
        return {"n": len(records), "ranked": ranked, "low_confidence": bool(low)}

    # -------------------------------------------------- interpretation ----
    def feature_importance(self, top_n: int = 10) -> pd.DataFrame:
        self._check_trained()
        names = self.pipeline.named_steps["prep"].get_feature_names_out()
        imp = self.pipeline.named_steps["tree"].feature_importances_
        out = (pd.DataFrame({"feature": names, "importance": imp})
                 .sort_values("importance", ascending=False).head(top_n))
        out["feature"] = out["feature"].str.replace(r"^(cat|num)__", "", regex=True)
        return out.reset_index(drop=True)

    def decision_rules(self, max_depth: int = 4) -> str:
        """Human-readable if/else rules (explainability for engineers)."""
        self._check_trained()
        names = self.pipeline.named_steps["prep"].get_feature_names_out()
        return export_text(self.pipeline.named_steps["tree"],
                           feature_names=list(names), max_depth=max_depth)

    # ----------------------------------------------------- persistence ----
    def save(self, path: str):
        import joblib
        self._check_trained()
        joblib.dump(self, path)

    @staticmethod
    def load(path: str) -> "RootCauseClassifier":
        import joblib
        return joblib.load(path)
