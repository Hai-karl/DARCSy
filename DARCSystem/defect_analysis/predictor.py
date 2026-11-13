"""Validation and prediction with the saved defect models (see train_model.py)."""
import os

import joblib
import pandas as pd

from .preprocess import DATE_FORMAT, TARGETS, TEXT_CATEGORICAL, input_columns


class PredictionError(ValueError):
    """Inputs are not valid. `problems` is a list of messages for the user."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


def model_path(model_dir, target):
    return os.path.join(model_dir, f"{target}.joblib")


def load_bundle(model_dir, target):
    path = model_path(model_dir, target)
    return joblib.load(path) if os.path.exists(path) else None


def _parse_date(value):
    for fmt in (DATE_FORMAT, "%Y-%m-%d"):
        try:
            return pd.to_datetime(str(value).strip(), format=fmt)
        except ValueError:
            continue
    return None


def validate_inputs(schema: dict, target: str, inputs) -> pd.DataFrame:
    """Check every field against the categories and ranges seen in the training data.
    Returns a one-row DataFrame in the column order the model expects."""
    if target not in TARGETS:
        raise PredictionError([f"target must be one of {list(TARGETS)}."])
    if not isinstance(inputs, dict):
        raise PredictionError(["inputs must be an object with one value per field."])
    wanted, problems, clean = input_columns(target), [], {}
    for key in inputs:
        if key not in wanted:
            if key == "repair_cost":
                problems.append("repair_cost is only known after the repair, so it is not used to predict "
                                f"{TARGETS[target]['label'].lower()}.")
            elif key == target:
                problems.append(f"{key} is the value being predicted, so it cannot also be an input.")
            else:
                problems.append(f"Unknown field '{key}'. Allowed fields: {wanted}.")
    for col in wanted:
        v = inputs.get(col)
        if v is None or (isinstance(v, str) and not v.strip()):
            problems.append(f"{col} is required.")
        elif col == "product_id":
            lo, hi = schema["product_id"]["min"], schema["product_id"]["max"]
            try:
                if isinstance(v, bool) or (isinstance(v, float) and not v.is_integer()):
                    raise ValueError
                n = int(str(v).strip()) if isinstance(v, str) else int(v)
            except ValueError:
                problems.append("product_id must be a whole number.")
                continue
            if not lo <= n <= hi:
                problems.append(f"product_id must be between {lo} and {hi}.")
            else:
                clean[col] = n
        elif col == "defect_date":
            d = _parse_date(v)
            lo, hi = schema["date"]["min"], schema["date"]["max"]
            if d is None:
                problems.append("defect_date must be a valid date, written M/D/YYYY or YYYY-MM-DD.")
            elif not pd.Timestamp(lo) <= d <= pd.Timestamp(hi):
                problems.append(f"defect_date must be between {lo} and {hi} (the dates in the training data).")
            else:
                clean[col] = str(d.date())
        else:
            allowed = schema["categories"][col]
            if not isinstance(v, str) or v.strip() not in allowed:
                problems.append(f"{col} must be one of {allowed}.")
            else:
                clean[col] = v.strip()
    if problems:
        raise PredictionError(problems)
    return pd.DataFrame([clean])[wanted]


def quality_note(meta: dict) -> dict:
    """Plain-language summary of how good a trained model is, shown next to every prediction."""
    m, b = meta["metrics"], meta["baseline_metrics"]
    if meta["task"] == "classification":
        summary = (f"{meta['selected_model']}: accuracy {m['accuracy']:.0%} on held-out data; "
                   f"always guessing the most common answer scores {b['accuracy']:.0%}.")
        warn = ("This model is no better than always guessing the most common answer, so the inputs "
                "do not predict this reliably. The percentages only reflect patterns memorised from the training rows, "
                "not real certainty. Treat results as a demonstration only.")
    else:
        summary = (f"{meta['selected_model']}: average error {m['mae']:.0f}, R² {m['r2']:.2f}; "
                   f"always guessing the average gives an error of {b['mae']:.0f}.")
        warn = ("This model is no better than always guessing the average cost, so the inputs "
                "do not predict this reliably. Treat results as a demonstration only.")
    return {"beats_baseline": meta["beats_baseline"], "summary": summary,
            "warning": None if meta["beats_baseline"] else warn, "model": meta["selected_model"],
            "trained_at": meta["trained_at"], "metrics": {k: v for k, v in m.items() if k != "confusion_matrix"}}


def predict(bundle: dict, inputs) -> dict:
    meta = bundle["meta"]
    X = validate_inputs(meta["schema"], meta["target"], inputs)
    pipe = bundle["pipeline"]
    out = {"target": meta["target"], "task": meta["task"], "quality": quality_note(meta)}
    if meta["task"] == "classification":
        proba = pipe.predict_proba(X)[0]
        probs = dict(sorted(zip(map(str, pipe.classes_), map(float, proba)), key=lambda kv: -kv[1]))
        top = next(iter(probs))
        out.update(prediction=top, confidence=probs[top], probabilities=probs)
    else:
        value, mae = float(pipe.predict(X)[0]), float(meta["metrics"]["mae"])
        lo, hi = meta["schema"]["repair_cost"]["min"], meta["schema"]["repair_cost"]["max"]
        out.update(prediction=round(value, 2), typical_error=round(mae, 2),
                   likely_range=[round(max(lo, value - mae), 2), round(min(hi, value + mae), 2)])
    return out
