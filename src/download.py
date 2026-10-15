"""Download Part D prescriber data (yearly) and the OIG exclusions list (monthly)."""
import datetime as dt

import pandas as pd
import requests

from .utils import log

PARTD_COLS = [
    "Prscrbr_NPI", "Prscrbr_Last_Org_Name", "Prscrbr_First_Name", "Prscrbr_State_Abrvtn",
    "Prscrbr_Type", "Tot_Clms", "Tot_30day_Fills", "Tot_Drug_Cst", "Tot_Day_Suply", "Tot_Benes",
    "Brnd_Tot_Clms", "Gnrc_Tot_Clms", "Opioid_Tot_Clms", "Opioid_LA_Tot_Clms",
    "Antbtc_Tot_Clms", "Antpsyct_GE65_Tot_Clms", "Bene_Avg_Age", "Bene_Avg_Risk_Scre",
]


def _stream_to_file(url, dest):
    log.info(f"Downloading {url}")
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    log.info(f"Saved {dest} ({dest.stat().st_size / 1e6:.1f} MB)")


def find_partd_urls(cfg, years):
    """Look up the CSV link for each year in the CMS data catalog."""
    urls = {int(k): v for k, v in (cfg["data"].get("partd_csv_urls") or {}).items()}
    missing = [y for y in years if y not in urls]
    if not missing:
        return urls

    catalog = requests.get(cfg["data"]["cms_catalog_url"], timeout=300).json()
    title = cfg["data"]["partd_dataset_title"]
    ds = next((d for d in catalog.get("dataset", []) if d.get("title") == title), None)
    if ds is None:
        raise RuntimeError(f"Couldn't find '{title}' in the CMS catalog. Add partd_csv_urls to config.yaml.")

    for dist in ds.get("distribution", []):
        link = dist.get("downloadURL") or ""
        is_csv = dist.get("mediaType") == "text/csv" or link.lower().endswith(".csv")
        if not is_csv:
            continue
        # distribution titles look like "Medicare Part D Prescribers - by Provider : 2021-12-31"
        dist_title = dist.get("title", "")
        for y in missing:
            if f": {y}-" in dist_title and y not in urls:
                urls[y] = link

    still_missing = [y for y in years if y not in urls]
    if still_missing:
        raise RuntimeError(f"No CSV link found for years {still_missing}. Add them to partd_csv_urls.")
    return urls


def download_partd(cfg, years=None):
    """Download each year, keep only needed columns (and dev_state if set), save as parquet."""
    years = years or cfg["model"]["train_years"]
    raw = cfg["data"]["raw_dir"]
    state = cfg["data"].get("dev_state")
    urls = find_partd_urls(cfg, years)

    for y in years:
        out = raw / f"partd_{y}{'_' + state if state else ''}.parquet"
        if out.exists():
            log.info(f"{out.name} already exists, skipping")
            continue
        csv_path = raw / f"partd_{y}.csv"
        if not csv_path.exists():
            _stream_to_file(urls[y], csv_path)

        parts = []
        for chunk in pd.read_csv(csv_path, usecols=lambda c: c in PARTD_COLS, dtype={"Prscrbr_NPI": str},
                                 chunksize=250_000, low_memory=False):
            if state:
                chunk = chunk[chunk["Prscrbr_State_Abrvtn"] == state]
            parts.append(chunk)
        df = pd.concat(parts, ignore_index=True)
        df["year"] = y
        df.to_parquet(out, index=False)
        log.info(f"{y}: {len(df):,} prescribers saved to {out.name}")
        csv_path.unlink()  # free disk space


def download_leie(cfg):
    """Always grab the latest exclusions file (it changes monthly)."""
    dest = cfg["data"]["raw_dir"] / f"leie_{dt.date.today():%Y%m}.csv"
    _stream_to_file(cfg["data"]["leie_url"], dest)
    return dest
