"""Check flagged providers against later OIG exclusions. This is the real-world test."""
import datetime as dt

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from .utils import hash_id, log, name_key


def load_exclusions(cfg, leie_path):
    leie = pd.read_csv(leie_path, dtype=str).fillna("")
    leie["excl_date"] = pd.to_datetime(leie["EXCLDATE"], format="%Y%m%d", errors="coerce")
    leie["has_npi"] = leie["NPI"].str.strip().str.strip("0") != ""
    leie["npi_hash"] = np.where(leie["has_npi"], leie["NPI"].map(hash_id), None)
    leie["name_key_hash"] = [hash_id(name_key(l, f, s)) for l, f, s in
                             zip(leie["LASTNAME"], leie["FIRSTNAME"], leie["STATE"])]
    leie["is_fraud_type"] = leie["EXCLTYPE"].str.strip().str.lower().isin(
        [t.lower() for t in cfg["validation"]["fraud_excl_types"]])
    return leie


def match(scores, leie, window_start):
    """Match by NPI first, then by name + state when OIG has no NPI on file."""
    after = leie[leie["excl_date"] >= window_start]
    before = leie[leie["excl_date"] < window_start]

    s = scores.copy()
    npi_after = after[after["has_npi"]].drop_duplicates("npi_hash").set_index("npi_hash")
    s["excl_date"] = s["provider_id"].map(npi_after["excl_date"])
    s["excl_type"] = s["provider_id"].map(npi_after["EXCLTYPE"])
    s["is_fraud_type"] = s["provider_id"].map(npi_after["is_fraud_type"])
    s["match_method"] = np.where(s["excl_date"].notna(), "NPI", None)

    # Backup name match, only when the name key is unique on both sides
    name_after = after[~after["has_npi"]]
    name_after = name_after[~name_after["name_key_hash"].duplicated(keep=False)].set_index("name_key_hash")
    unique_names = s["name_key_hash"].map(s["name_key_hash"].value_counts()) == 1
    need = s["excl_date"].isna() & unique_names & s["name_key_hash"].isin(name_after.index)
    s.loc[need, "excl_date"] = s.loc[need, "name_key_hash"].map(name_after["excl_date"])
    s.loc[need, "excl_type"] = s.loc[need, "name_key_hash"].map(name_after["EXCLTYPE"])
    s.loc[need, "is_fraud_type"] = s.loc[need, "name_key_hash"].map(name_after["is_fraud_type"])
    s.loc[need, "match_method"] = "Name + state"

    # Anyone already excluded BEFORE the window shouldn't count either way
    already = set(before.loc[before["has_npi"], "npi_hash"])
    s = s[~s["provider_id"].isin(already)].copy()

    s["excluded_after"] = s["excl_date"].notna()
    s["excluded_fraud_after"] = s["excluded_after"] & s["is_fraud_type"].fillna(False).astype(bool)
    return s


def lift_table(s, top_pcts):
    rows = []
    for target in ["excluded_after", "excluded_fraud_after"]:
        base = s[target].mean()
        total_pos = s[target].sum()
        for p in top_pcts:
            top = s[s["anomaly_pct_rank"] >= 100 - p]
            hits = int(top[target].sum())
            rate = top[target].mean() if len(top) else 0
            rows.append({
                "outcome": "Any exclusion" if target == "excluded_after" else "Fraud-type exclusion",
                "top_pct": p, "providers_in_group": len(top), "excluded_in_group": hits,
                "group_rate_pct": round(rate * 100, 3), "baseline_rate_pct": round(base * 100, 3),
                "lift": round(rate / base, 2) if base > 0 else None,
                "share_of_all_exclusions_caught_pct": round(hits / total_pos * 100, 1) if total_pos else None,
            })
    return pd.DataFrame(rows)


def run_validation(cfg, scores, leie_path):
    window = pd.Timestamp(cfg["validation"]["window_start"])
    leie = load_exclusions(cfg, leie_path)
    s = match(scores, leie, window)
    lifts = lift_table(s, cfg["validation"]["top_pcts"])

    auc = None
    if 0 < s["excluded_after"].sum() < len(s):
        auc = roc_auc_score(s["excluded_after"], s["anomaly_score"])

    summary = {
        "run_date": dt.date.today().isoformat(),
        "providers_scored": len(s),
        "flagged": int(s["flagged"].sum()),
        "excluded_since_window": int(s["excluded_after"].sum()),
        "flagged_and_excluded": int((s["flagged"] & s["excluded_after"]).sum()),
        "flagged_and_fraud_excluded": int((s["flagged"] & s["excluded_fraud_after"]).sum()),
        "matched_by_name": int((s["match_method"] == "Name + state").sum()),
        "auc": round(auc, 4) if auc is not None else None,
        "leie_file": leie_path.name,
    }
    log.info(f"Validation: {summary}")
    return s, lifts, summary
