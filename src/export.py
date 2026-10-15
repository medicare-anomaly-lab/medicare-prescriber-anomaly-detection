"""Write small, dashboard-ready tables to outputs/ and (optionally) Google Sheets."""
import json
import os

import pandas as pd

from .utils import log


def build_tables(cfg, s, lifts, summary):
    pct = cfg["export"]["flagged_export_pct"]
    s = s.copy()
    s["excl_date"] = pd.to_datetime(s["excl_date"]).dt.date

    top = s[s["anomaly_pct_rank"] >= 100 - pct].sort_values("anomaly_score", ascending=False)
    flagged_cols = ["provider_id", "state", "specialty", "tot_claims", "anomaly_score", "anomaly_pct_rank",
                    "flagged", "top_reasons", "pc1", "pc2", "opioid_share", "brand_share",
                    "cost_per_claim", "claims_per_bene", "excluded_after", "excluded_fraud_after",
                    "excl_date", "excl_type", "match_method"]
    top_providers = top[flagged_cols]

    def summarize(by):
        g = s.groupby(by)
        return pd.DataFrame({
            "providers": g.size(),
            "flagged": g["flagged"].sum(),
            "flagged_rate_pct": (g["flagged"].mean() * 100).round(2),
            "excluded_after": g["excluded_after"].sum(),
            "flagged_and_excluded": g.apply(lambda d: (d["flagged"] & d["excluded_after"]).sum(),
                                            include_groups=False),
            "avg_anomaly_score": g["anomaly_score"].mean().round(4),
        }).reset_index().sort_values("flagged", ascending=False)

    # A random sample of everyone for "flagged vs normal" scatterplots
    sample = s.sample(min(len(s), 20_000), random_state=0)[
        ["provider_id", "specialty", "pc1", "pc2", "anomaly_score", "flagged", "excluded_after"]]

    return {
        "top_providers": top_providers,
        "by_specialty": summarize("specialty"),
        "by_state": summarize("state"),
        "lift": lifts,
        "scatter_sample": sample,
        "run_summary": pd.DataFrame([summary]),
    }


def write_outputs(cfg, tables):
    out = cfg["data"]["output_dir"]
    for name, df in tables.items():
        if name == "run_summary":
            continue
        df.to_csv(out / f"{name}.csv", index=False)

    # Scoreboard keeps one row per run so you can chart it over time
    hist_path = out / "scoreboard_history.csv"
    new = tables["run_summary"]
    if hist_path.exists():
        hist = pd.read_csv(hist_path)
        hist = hist[hist["run_date"] != new["run_date"].iloc[0]]
        new = pd.concat([hist, new], ignore_index=True)
    new.to_csv(hist_path, index=False)
    tables["scoreboard_history"] = new
    log.info(f"Wrote {len(tables)} tables to {out}")


def push_to_google_sheets(tables):
    """Tableau Public can auto-refresh from Google Sheets. Skips quietly if secrets aren't set."""
    creds, sheet_id = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"), os.environ.get("GOOGLE_SHEET_ID")
    if not creds or not sheet_id:
        log.info("Google Sheets secrets not set, skipping upload")
        return
    import gspread

    gc = gspread.service_account_from_dict(json.loads(creds))
    sh = gc.open_by_key(sheet_id)
    for name, df in tables.items():
        if name == "run_summary":
            continue
        try:
            ws = sh.worksheet(name)
            ws.clear()
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=name, rows=1, cols=1)
        clean = df.astype(object).where(df.notna(), "")
        ws.update([clean.columns.tolist()] + clean.astype(str).values.tolist())
        log.info(f"Google Sheet tab '{name}' updated ({len(df):,} rows)")
