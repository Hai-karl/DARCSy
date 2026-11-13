"""Shared configuration for the Defect Rate Trend Analysis and Root Cause
Identification System.

Scope note: the system analyses ALREADY-RECORDED structured defect data entered
by human inspectors. It does not process images or sensor streams.
"""

# ---- Record schema (one row = one inspection batch record) -----------------
REQUIRED_COLUMNS = [
    "inspection_date",   # date of inspection
    "production_line",   # e.g. "Line A"
    "product_type",      # e.g. "Housing"
    "shift",             # Morning / Evening / Night
    "machine_id",        # e.g. "M-03"
    "defect_type",       # e.g. "Scratch"; "None" when defect_count == 0
    "units_inspected",   # > 0
    "defect_count",      # quantity: 0 <= defect_count <= units_inspected
    "batch_number",      # production/material batch for traceability
    "severity",          # Minor / Major / Critical ("None" when defect_count == 0)
]

OPTIONAL_COLUMNS = [
    "temperature",       # numeric process factor (deg C)
    "humidity",          # numeric process factor (% RH)
    "machine_age_months",
    "root_cause",        # label (5M category); required only for model training
]

NUMERIC_FACTORS = ["temperature", "humidity", "machine_age_months"]
# batch_number is stored for traceability but not used as a model feature (too many unique values)
CATEGORICAL_FEATURES = ["defect_type", "severity", "production_line", "product_type",
                        "shift", "machine_id"]

SEVERITY_LEVELS = ["Minor", "Major", "Critical", "Safety-Critical"]

# Root-cause categories (5M + Environment framework)
ROOT_CAUSES = ["Man", "Machine", "Material", "Method", "Environment"]

NO_DEFECT_LABEL = "None"

# ---- Role-Based Access Control --------------------------------------------
ROLES = ["QC Engineer", "Line Supervisor", "Quality Manager", "IT Administrator"]

PERMISSIONS = {
    "QC Engineer": {"record:create", "record:read", "record:update", "dashboard:view",
                    "rootcause:predict", "alert:view", "action:view", "action:log", "report:export"},
    "Line Supervisor": {"record:read", "dashboard:view", "rootcause:predict",
                        "alert:view", "alert:ack", "action:view"},
    "Quality Manager": {"record:read", "dashboard:view", "rootcause:predict", "rootcause:train",
                        "report:export", "alert:view", "alert:ack", "action:view",
                        "action:approve", "threshold:configure", "sus:view"},
    "IT Administrator": {"record:read", "record:delete", "user:manage", "system:configure", "sus:view"},
}

# ---- Statistical defaults --------------------------------------------------
PARETO_CUTOFF = 0.80          # "vital few" threshold
CONTROL_CHART_SIGMA = 3.0
MIN_TRAINING_ROWS = 30
