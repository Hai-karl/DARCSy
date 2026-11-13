"""Centralised defect record management: validation, cleaning, loading."""
import pandas as pd

from .config import (NO_DEFECT_LABEL, OPTIONAL_COLUMNS, REQUIRED_COLUMNS,
                     ROOT_CAUSES, SEVERITY_LEVELS)


class ValidationError(ValueError):
    """Raised when defect records fail validation."""


def validate_records(df: pd.DataFrame) -> list:
    """Return a list of human-readable problems (empty list = valid)."""
    problems = []
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return [f"Missing required columns: {missing}"]

    if df[REQUIRED_COLUMNS].isnull().any().any():
        bad = df[REQUIRED_COLUMNS].isnull().sum()
        problems.append(f"Null values in required columns: {bad[bad > 0].to_dict()}")
        return problems

    dates = pd.to_datetime(df["inspection_date"], errors="coerce")
    if dates.isnull().any():
        problems.append(f"{int(dates.isnull().sum())} rows have an invalid inspection_date.")

    units = pd.to_numeric(df["units_inspected"], errors="coerce")
    count = pd.to_numeric(df["defect_count"], errors="coerce")
    if units.isnull().any() or (units <= 0).any():
        problems.append("units_inspected must be a number greater than 0.")
    if count.isnull().any() or (count < 0).any():
        problems.append("defect_count must be a number >= 0.")
    if (count > units).any():
        problems.append("defect_count cannot exceed units_inspected.")

    zero_but_typed = (count == 0) & (df["defect_type"] != NO_DEFECT_LABEL)
    if zero_but_typed.any():
        problems.append(f"{int(zero_but_typed.sum())} rows have defect_count = 0 "
                        f"but defect_type is not '{NO_DEFECT_LABEL}'.")

    bad_sev = (count > 0) & ~df["severity"].isin(SEVERITY_LEVELS)
    if bad_sev.any():
        problems.append(f"{int(bad_sev.sum())} rows with defects need a severity of {SEVERITY_LEVELS}.")
    sev_on_clean = (count == 0) & (df["severity"] != NO_DEFECT_LABEL)
    if sev_on_clean.any():
        problems.append(f"{int(sev_on_clean.sum())} rows have defect_count = 0 "
                        f"but severity is not '{NO_DEFECT_LABEL}'.")
    if (df["batch_number"].astype(str).str.strip() == "").any():
        problems.append("batch_number cannot be blank.")

    if "root_cause" in df.columns:
        labelled = df["root_cause"].dropna()
        unknown = set(labelled) - set(ROOT_CAUSES)
        if unknown:
            problems.append(f"Unknown root_cause labels: {sorted(unknown)}")
    return problems


def prepare_records(df: pd.DataFrame, strict: bool = True) -> pd.DataFrame:
    """Validate, type-cast and add the derived `defect_rate` column."""
    problems = validate_records(df)
    if problems and strict:
        raise ValidationError("; ".join(problems))

    out = df.copy()
    out["inspection_date"] = pd.to_datetime(out["inspection_date"])
    out["units_inspected"] = pd.to_numeric(out["units_inspected"]).astype(int)
    out["defect_count"] = pd.to_numeric(out["defect_count"]).astype(int)
    for col in OPTIONAL_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    out["defect_rate"] = out["defect_count"] / out["units_inspected"]
    return out.sort_values("inspection_date").reset_index(drop=True)


def load_records(path: str, strict: bool = True) -> pd.DataFrame:
    """Load defect records from CSV or Excel and prepare them."""
    if path.lower().endswith((".xlsx", ".xls")):
        raw = pd.read_excel(path)
    else:
        raw = pd.read_csv(path)
    return prepare_records(raw, strict=strict)


def filter_records(df, start=None, end=None, production_line=None,
                   product_type=None, shift=None, machine_id=None):
    """Apply the dashboard filters; any argument left as None is ignored."""
    mask = pd.Series(True, index=df.index)
    if start is not None:
        mask &= df["inspection_date"] >= pd.to_datetime(start)
    if end is not None:
        mask &= df["inspection_date"] <= pd.to_datetime(end)
    for col, val in [("production_line", production_line),
                     ("product_type", product_type),
                     ("shift", shift), ("machine_id", machine_id)]:
        if val is not None:
            mask &= df[col] == val
    return df[mask].reset_index(drop=True)
