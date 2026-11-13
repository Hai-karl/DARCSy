"""API for the dataset prediction module (models trained from data/defects_data.csv)."""
import os

from flask import jsonify, request

from defect_analysis.predictor import PredictionError, load_bundle, model_path, predict, quality_note
from defect_analysis.preprocess import TARGETS, SchemaError, input_columns, load_dataset, schema_from_data
from defect_analysis.train_model import train_all

from .auth import auth_required


def register_ml(app):
    cache = {}

    def bundle(target):
        path = model_path(app.config["ML_MODEL_DIR"], target)
        if not os.path.exists(path):
            return None
        stamp = os.path.getmtime(path)
        if cache.get(target, (None, None))[0] != stamp:
            cache[target] = (stamp, load_bundle(app.config["ML_MODEL_DIR"], target))
        return cache[target][1]

    @app.get("/api/ml/schema")
    @auth_required("rootcause:predict")
    def ml_schema():
        trained = {t: bundle(t) for t in TARGETS}
        schema = next((b["meta"]["schema"] for b in trained.values() if b), None)
        if schema is None:                                    # not trained yet: read options from the data file
            try:
                schema = schema_from_data(load_dataset(app.config["ML_DATA_PATH"]))
            except (OSError, SchemaError) as e:
                return jsonify(error=f"Dataset not available: {e}"), 404
        return jsonify(schema=schema, targets=[
            {"key": t, "label": TARGETS[t]["label"], "task": TARGETS[t]["task"], "inputs": input_columns(t),
             "trained": b is not None, "quality": quality_note(b["meta"]) if b else None}
            for t, b in trained.items()])

    @app.post("/api/ml/predict")
    @auth_required("rootcause:predict")
    def ml_predict():
        body = request.get_json(silent=True) or {}
        target = body.get("target")
        if target not in TARGETS:
            return jsonify(error=f"target must be one of {list(TARGETS)}."), 422
        b = bundle(target)
        if b is None:
            return jsonify(error="This model is not trained yet. A Quality Manager can train it first."), 409
        try:
            return jsonify(predict(b, body.get("inputs")))
        except PredictionError as e:
            return jsonify(error="Please correct the highlighted fields.", problems=e.problems), 422

    @app.get("/api/ml/metrics")
    @auth_required("rootcause:predict")
    def ml_metrics():
        return jsonify([b["meta"] for t in TARGETS if (b := bundle(t))])

    @app.post("/api/ml/train")
    @auth_required("rootcause:train")
    def ml_train():
        try:
            reports = train_all(app.config["ML_DATA_PATH"], app.config["ML_MODEL_DIR"],
                                n_estimators=app.config["ML_TREES"])
        except (OSError, SchemaError) as e:
            return jsonify(error=f"Training failed: {e}"), 422
        cache.clear()
        return jsonify([{"target": r["target"], "selected_model": r["selected_model"],
                         "beats_baseline": r["beats_baseline"], **quality_note(r)} for r in reports])
