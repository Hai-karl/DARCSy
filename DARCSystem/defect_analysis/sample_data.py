"""Synthetic defect-record generator for development and testing.

Embeds realistic patterns so the analytics have something to find:
  * Machine M-03 is worn -> Scratch/Dent defects, root cause 'Machine'
  * High humidity -> Corrosion defects, root cause 'Environment'
  * Night shift -> more Misalignment, root cause 'Man'
  * Material batch problems -> Crack defects, root cause 'Material'
  * A gradual upward drift in the defect rate from mid-period
Replace with real MySQL/CSV data in FYP2.
"""
import numpy as np
import pandas as pd

from .config import NO_DEFECT_LABEL


def generate_sample_records(n_days: int = 180, seed: int = 7,
                            start: str = "2026-01-05") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    lines = ["Line A", "Line B", "Line C"]
    products = ["Housing", "Bracket", "Panel"]
    shifts = ["Morning", "Evening", "Night"]
    machines = {"Line A": ["M-01", "M-02"], "Line B": ["M-03", "M-04"], "Line C": ["M-05", "M-06"]}
    age = {"M-01": 12, "M-02": 20, "M-03": 84, "M-04": 30, "M-05": 18, "M-06": 40}
    dates = pd.date_range(start, periods=n_days, freq="D")

    rows = []
    for d_i, date in enumerate(dates):
        if date.dayofweek == 6:        # no Sunday production
            continue
        drift = 1 + 0.6 * max(0, d_i - n_days / 2) / (n_days / 2)
        for line in lines:
            for shift in shifts:
                machine = rng.choice(machines[line])
                temp = rng.normal(27, 3)
                hum = np.clip(rng.normal(60, 12), 30, 95)
                units = int(rng.integers(180, 320))

                p_machine = 0.02 + (0.035 if machine == "M-03" else 0.0)
                p_env = 0.004 + max(0, hum - 70) * 0.0025
                p_man = 0.006 + (0.012 if shift == "Night" else 0.0)
                p_mat = 0.005 + (0.01 if rng.random() < 0.08 else 0.0)

                causes = {"Machine": p_machine, "Environment": p_env,
                          "Man": p_man, "Material": p_mat}
                # defect types overlap across causes so the model must also use
                # machine / shift / humidity context (not just defect_type)
                type_for = {"Machine": ["Scratch", "Dent", "Dent", "Misalignment"],
                            "Environment": ["Corrosion", "Corrosion", "Scratch"],
                            "Man": ["Misalignment", "Misalignment", "Scratch", "Dent"],
                            "Material": ["Crack", "Crack", "Dent", "Corrosion"]}
                # each cause-specific sub-batch inspects its own share of units,
                # so units_inspected is never double counted
                sub_units = units // 4
                batch = f"B{date:%y%m%d}-{line[-1]}{shift[0]}"
                for cause, p in causes.items():
                    cnt = int(rng.binomial(sub_units, min(p * drift, 0.5)))
                    base = dict(
                        inspection_date=date, production_line=line,
                        product_type=rng.choice(products), shift=shift,
                        machine_id=machine, units_inspected=sub_units, batch_number=batch,
                        temperature=round(temp, 1), humidity=round(hum, 1),
                        machine_age_months=age[machine])
                    if cnt == 0:
                        rows.append({**base, "defect_type": NO_DEFECT_LABEL,
                                     "defect_count": 0, "severity": NO_DEFECT_LABEL,
                                     "root_cause": None})
                    else:
                        rows.append({**base, "defect_type": rng.choice(type_for[cause]),
                                     "defect_count": cnt,
                                     "severity": rng.choice(["Minor", "Major", "Critical", "Safety-Critical"], p=[.64, .28, .07, .01]),
                                     "root_cause": cause})
    return pd.DataFrame(rows)
