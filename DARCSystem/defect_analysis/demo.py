"""Run:  python -m defect_analysis.demo   (from the folder containing the package)"""
from defect_analysis import *

df = prepare_records(generate_sample_records())
s = dashboard_summary(df, role="Quality Manager")
print(f"Overall defect rate: {s['overall_defect_rate']:.2%}")
print("Trend:", s["trend_direction"])
print("\nPareto (defect type):\n", s["pareto_defect_type"].round(1))
print("\nPearson correlations:\n", s["correlations"].round(3))
print("\nOut-of-control weeks:", int(s["control_chart"]["out_of_control"].sum()),
      "of", len(s["control_chart"]))

model = train_root_cause_model(df, role="Quality Manager")
print("\nModel accuracy: %.3f  F1: %.3f" % (model.metrics_["accuracy"], model.metrics_["f1_weighted"]))
print(model.feature_importance(6).round(3))
sample = df[df.defect_count > 0].tail(3)
print("\nSuggestions:\n", suggest_root_causes(model, sample, role="Line Supervisor").round(2))
