"""
Run the pipeline.

  python run_pipeline.py --stage full      # yearly: download Part D, rebuild features, retrain, validate, export
  python run_pipeline.py --stage monthly   # monthly: new exclusions list, re-validate saved scores, export
  python run_pipeline.py --stage full --sample   # test everything on fake data, no downloads
"""
import argparse
import sys

import pandas as pd

from src import download, export, features, model, validate
from src.utils import ROOT, load_config, log


def latest_leie(cfg):
    files = sorted(cfg["data"]["raw_dir"].glob("leie_*.csv"))
    if not files:
        sys.exit("No exclusions file found. Run without --sample or generate sample data first.")
    return files[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["full", "monthly"], default="monthly")
    ap.add_argument("--sample", action="store_true", help="use fake data from scripts/make_sample_data.py")
    args = ap.parse_args()
    cfg = load_config()

    if args.sample:
        from scripts.make_sample_data import make_sample
        make_sample(cfg)

    if args.stage == "full":
        if not args.sample:
            download.download_partd(cfg)
        feats = features.build_features(cfg)
        mdl, scored = model.train_and_score(cfg, feats)
        model.save_store(cfg, mdl, scored)

    store_file = cfg["data"]["store_dir"] / "scores.parquet"
    if not store_file.exists():
        sys.exit("No saved scores yet. Run --stage full first.")
    scores = pd.read_parquet(store_file)

    leie_path = latest_leie(cfg) if args.sample else download.download_leie(cfg)
    s, lifts, summary = validate.run_validation(cfg, scores, leie_path)

    tables = export.build_tables(cfg, s, lifts, summary)
    export.write_outputs(cfg, tables)
    export.push_to_google_sheets(tables)
    log.info("Done.")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
