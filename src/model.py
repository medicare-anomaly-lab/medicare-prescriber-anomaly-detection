"""Unsupervised anomaly detection + explanations + 2D coordinates for plotting."""
import joblib
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest

from .features import FEATURES
from .utils import hash_id, log, name_key

READABLE = {
    "log_claims": "Prescription volume", "log_cost": "Total drug cost",
    "claims_per_bene": "Prescriptions per patient", "cost_per_claim": "Cost per prescription",
    "days_per_claim": "Days supply per prescription", "brand_share": "Brand-name share",
    "opioid_share": "Opioid share", "opioid_la_share": "Long-acting opioid share",
    "antibiotic_share": "Antibiotic share", "antipsych_share": "Antipsychotic share (65+)",
    "bene_risk": "Patient risk score", "claims_growth": "Growth in prescriptions",
}


def train_and_score(cfg, feats):
    zcols = [f"z_{c}" for c in FEATURES]
    X = feats[zcols].to_numpy()

    m = cfg["model"]
    model = IsolationForest(n_estimators=m["n_estimators"], contamination=m["contamination"],
                            random_state=m["random_state"], n_jobs=-1).fit(X)

    out = feats.copy()
    out["anomaly_score"] = -model.score_samples(X)          # higher = weirder
    out["anomaly_pct_rank"] = out["anomaly_score"].rank(pct=True) * 100
    out["flagged"] = model.predict(X) == -1

    # Why was each provider flagged? Top 3 features furthest from peers.
    absz = np.abs(X)
    top3 = np.argsort(-absz, axis=1)[:, :3]
    def reasons(i):
        bits = []
        for j in top3[i]:
            z = X[i, j]
            if abs(z) < 2:
                continue
            bits.append(f"{READABLE[FEATURES[j]]} {'high' if z > 0 else 'low'} ({z:+.1f})")
        return "; ".join(bits) or "Unusual mix of features"
    out["top_reasons"] = [reasons(i) for i in range(len(out))]

    # 2D coordinates for a scatterplot in the dashboards
    pcs = PCA(n_components=2, random_state=m["random_state"]).fit_transform(X)
    out["pc1"], out["pc2"] = pcs[:, 0], pcs[:, 1]

    log.info(f"Flagged {out['flagged'].sum():,} of {len(out):,} prescribers")
    return model, out


def save_store(cfg, model, scored):
    """Save results with hashed IDs only, so the repo can stay public."""
    store = cfg["data"]["store_dir"]
    keep = pd.DataFrame({
        "provider_id": scored["npi"].map(hash_id),
        "name_key_hash": [hash_id(name_key(l, f, s)) for l, f, s in
                          zip(scored["last"], scored["first"], scored["state"])],
        "state": scored["state"],
        "specialty": scored["specialty"],
        "peer_group": scored["peer_group"],
        "tot_claims": scored["tot_claims"].round(0),
        "anomaly_score": scored["anomaly_score"].round(5),
        "anomaly_pct_rank": scored["anomaly_pct_rank"].round(3),
        "flagged": scored["flagged"],
        "top_reasons": scored["top_reasons"],
        "pc1": scored["pc1"].round(4), "pc2": scored["pc2"].round(4),
    })
    for c in FEATURES:
        keep[c] = scored[c].round(4)
    keep.to_parquet(store / "scores.parquet", index=False)
    joblib.dump(model, store / "model.joblib")
    log.info(f"Saved {len(keep):,} hashed scores to {store / 'scores.parquet'}")
    return keep
