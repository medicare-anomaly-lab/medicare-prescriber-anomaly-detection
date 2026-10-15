"""Turn raw Part D rows into per-prescriber features compared against specialty peers."""
import numpy as np
import pandas as pd

from .utils import log

FEATURES = [
    "log_claims", "log_cost", "claims_per_bene", "cost_per_claim", "days_per_claim",
    "brand_share", "opioid_share", "opioid_la_share", "antibiotic_share",
    "antipsych_share", "bene_risk", "claims_growth",
]


def _safe_div(a, b):
    a, b = a.astype(float), b.astype(float)
    return np.where(b > 0, a / b, 0.0)


def load_years(cfg, years):
    raw = cfg["data"]["raw_dir"]
    state = cfg["data"].get("dev_state")
    frames = []
    for y in years:
        path = raw / f"partd_{y}{'_' + state if state else ''}.parquet"
        frames.append(pd.read_parquet(path))
    return pd.concat(frames, ignore_index=True)


def yearly_features(df):
    # CMS hides small counts (1-10) as blanks. Treat them as 0 for share calculations.
    count_cols = ["Tot_Clms", "Tot_Drug_Cst", "Tot_Day_Suply", "Tot_Benes", "Brnd_Tot_Clms",
                  "Opioid_Tot_Clms", "Opioid_LA_Tot_Clms", "Antbtc_Tot_Clms", "Antpsyct_GE65_Tot_Clms"]
    for c in count_cols:
        df[c] = pd.to_numeric(df.get(c, 0), errors="coerce").fillna(0)
    df["Bene_Avg_Risk_Scre"] = pd.to_numeric(df.get("Bene_Avg_Risk_Scre"), errors="coerce")

    f = pd.DataFrame({
        "npi": df["Prscrbr_NPI"].astype(str),
        "year": df["year"],
        "last": df["Prscrbr_Last_Org_Name"],
        "first": df["Prscrbr_First_Name"],
        "state": df["Prscrbr_State_Abrvtn"],
        "specialty": df["Prscrbr_Type"].fillna("Unknown"),
        "tot_claims": df["Tot_Clms"],
        "log_claims": np.log1p(df["Tot_Clms"]),
        "log_cost": np.log1p(df["Tot_Drug_Cst"]),
        "claims_per_bene": _safe_div(df["Tot_Clms"], df["Tot_Benes"]),
        "cost_per_claim": _safe_div(df["Tot_Drug_Cst"], df["Tot_Clms"]),
        "days_per_claim": _safe_div(df["Tot_Day_Suply"], df["Tot_Clms"]),
        "brand_share": _safe_div(df["Brnd_Tot_Clms"], df["Tot_Clms"]),
        "opioid_share": _safe_div(df["Opioid_Tot_Clms"], df["Tot_Clms"]),
        "opioid_la_share": _safe_div(df["Opioid_LA_Tot_Clms"], df["Opioid_Tot_Clms"]),
        "antibiotic_share": _safe_div(df["Antbtc_Tot_Clms"], df["Tot_Clms"]),
        "antipsych_share": _safe_div(df["Antpsyct_GE65_Tot_Clms"], df["Tot_Clms"]),
        "bene_risk": df["Bene_Avg_Risk_Scre"],
    })
    return f


def build_features(cfg, years=None):
    years = years or cfg["model"]["train_years"]
    yf = yearly_features(load_years(cfg, years))

    # Growth: how much claims changed from first to last year in the window
    first_last = yf.sort_values("year").groupby("npi")["tot_claims"].agg(["first", "last"])
    growth = np.log1p(first_last["last"]) - np.log1p(first_last["first"])

    num = [c for c in FEATURES if c != "claims_growth"] + ["tot_claims"]
    agg = yf.groupby("npi")[num].mean()
    info = yf.sort_values("year").groupby("npi")[["last", "first", "state", "specialty"]].last()
    feats = info.join(agg)
    feats["claims_growth"] = growth
    feats["n_years"] = yf.groupby("npi")["year"].nunique()
    feats["bene_risk"] = feats["bene_risk"].fillna(feats["bene_risk"].median())

    feats = feats[feats["tot_claims"] >= cfg["model"]["min_total_claims"]].copy()

    # Pool small specialties so every peer group is big enough to compare against
    counts = feats["specialty"].value_counts()
    small = counts[counts < cfg["model"]["min_peer_group_size"]].index
    feats["peer_group"] = feats["specialty"].where(~feats["specialty"].isin(small), "Other")

    # Robust z-score within peer group: how far from a typical peer?
    def robust_z(s):
        med = s.median()
        mad = (s - med).abs().median() * 1.4826
        if mad == 0:
            mad = s.std() or 1.0
        return ((s - med) / mad).clip(-10, 10)

    for c in FEATURES:
        feats[f"z_{c}"] = feats.groupby("peer_group")[c].transform(robust_z).fillna(0)

    log.info(f"Built features for {len(feats):,} prescribers in {feats['peer_group'].nunique()} peer groups")
    return feats.reset_index()
