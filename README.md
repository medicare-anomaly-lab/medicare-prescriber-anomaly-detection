# Medicare Prescriber Anomaly Detection

Unsupervised anomaly detection on Medicare Part D prescribing data, validated against real-world outcomes: do the prescribers our model flags as unusual later get excluded from Medicare by the HHS Office of Inspector General (OIG)?

The pipeline refreshes automatically every month with GitHub Actions, and the results feed live Power BI and Tableau dashboards.

## How it works

1. **Data.** CMS Medicare Part D Prescribers by Provider (yearly, one row per prescriber) and the OIG List of Excluded Individuals/Entities, LEIE (monthly).
2. **Features.** For each prescriber, averaged over the training years: prescription volume, cost per prescription, prescriptions per patient, days supply, brand-name share, opioid and long-acting opioid share, antibiotic and antipsychotic share, patient risk score, and growth over time.
3. **Peer comparison.** Every feature is converted to a robust z-score within the prescriber's specialty, so a pain specialist is compared to other pain specialists, not to dentists.
4. **Model.** Isolation Forest flags the most unusual prescribers. Each flagged prescriber gets its top reasons (the features furthest from their peers), plus PCA coordinates for plotting.
5. **Validation.** The model trains on 2019 to 2021 data. We then check who was excluded by OIG from 2022 onward, which the model never saw. Results are reported as lift: how many times more likely a flagged prescriber is to be excluded than a typical one.

## Folder structure

```
config.yaml                 all settings (years, state filter, thresholds)
run_pipeline.py             entry point
src/
  download.py               pulls Part D (via the CMS catalog) and the LEIE
  features.py               builds per-prescriber features and peer z-scores
  model.py                  Isolation Forest, explanations, PCA, hashed results store
  validate.py               matches against OIG exclusions, computes lift and AUC
  export.py                 writes dashboard tables to outputs/ and Google Sheets
scripts/make_sample_data.py fake data for testing in seconds
data/raw/                   big downloads (not committed)
data/store/                 hashed model results (committed, needed for monthly runs)
outputs/                    tables the dashboards read (committed)
.github/workflows/refresh.yml   the schedule
```

## Running it locally

```bash
pip install -r requirements.txt

# test the whole thing on fake data first (no downloads)
python run_pipeline.py --stage full --sample

# real data: download Part D, train, validate, export
python run_pipeline.py --stage full

# monthly: grab the newest exclusions list and re-validate
python run_pipeline.py --stage monthly
```

`config.yaml` has `dev_state: "NC"` so the first real runs stay small and fast. Once everything works, set it to `null` to run on the whole country.

Before the first real run, delete the sample results so they don't mix with real ones: everything in `outputs/` and `data/store/`, plus `data/raw/leie_sample.csv` and the sample `partd_*.parquet` files.

## Setting up GitHub (one time)

1. **Create the repo.** One person creates a **public** repo on their personal account and uploads these files. Public keeps GitHub Actions free and lets recruiters see it.
2. **Add your partner.** Settings > Collaborators > Add people.
3. **Add secrets.** Settings > Secrets and variables > Actions > New repository secret:
   - `PRIVATE_SALT`: any long random string. This is what makes the hashed provider IDs impossible to reverse, so never commit it. Keep a copy somewhere safe, because changing it breaks matching against saved results.
   - `GOOGLE_SERVICE_ACCOUNT_JSON` and `GOOGLE_SHEET_ID`: only needed for the Tableau auto-refresh (see below).
4. **First run.** Actions tab > Refresh pipeline > Run workflow > choose `full`.

After that it runs on its own: monthly on the 15th, and a full retrain every July 1. Each run commits the updated `outputs/` back to the repo.

**Each new year:** when CMS releases a new year of Part D data, update `train_years` and `window_start` in `config.yaml` if you want to roll the window forward.

## Connecting the dashboards

**Power BI** reads the CSVs straight from GitHub:
Get Data > Web > paste the raw file link, for example
`https://raw.githubusercontent.com/<username>/<repo>/main/outputs/top_providers.csv`
Do this for each table, publish to the Power BI service, then set a scheduled refresh in the dataset settings. Publishing and scheduled refresh usually need a Pro license, so check what UNCW's Microsoft account includes.

**Tableau Public** auto-refreshes from Google Sheets:
1. Create an empty Google Sheet and copy its ID from the URL (the long string between `/d/` and `/edit`).
2. In Google Cloud, create a service account, enable the Google Sheets API, and download its JSON key.
3. Share the Google Sheet with the service account's email as an Editor.
4. Paste the full JSON key into the `GOOGLE_SERVICE_ACCOUNT_JSON` secret and the sheet ID into `GOOGLE_SHEET_ID`.
5. In Tableau Public, connect to the Google Sheet and turn on "Keep this data in sync" when you publish.

## Output tables

| File | What it is |
|---|---|
| `top_providers.csv` | Top 5% most anomalous prescribers: hashed ID, specialty, state, score, reasons, and whether they were later excluded |
| `lift.csv` | The headline result: lift for the top 0.5/1/2/5%, for any exclusion and for fraud-type exclusions |
| `by_specialty.csv`, `by_state.csv` | Flag and exclusion counts by group, good for maps and bar charts |
| `scatter_sample.csv` | 20k-row sample with PCA coordinates for a flagged-vs-normal scatterplot |
| `scoreboard_history.csv` | One row per run, so you can chart flagged-and-excluded growing over time |

## Privacy

No names or NPIs are saved anywhere in this repo or the dashboards. Every provider is a salted hash, and matching against the OIG list is done on hashes too. Being statistically unusual is not evidence of wrongdoing (some specialists just treat unusual patients), so we don't think it's right to publish flagged doctors by name.

## Limitations

- The OIG file only contains exclusions currently in effect. People who were later reinstated are missing, which slightly undercounts true hits.
- Many OIG records have no NPI. We fall back to matching on last name, first name, and state, only when that combination is unique on both sides.
- Not every exclusion is fraud (some are license revocations or patient abuse). `fraud_excl_types` in `config.yaml` filters to fraud-related types. Double check those codes against OIG's list of exclusion authorities.
- CMS hides counts between 1 and 10 for privacy. Those are treated as 0.
- Exclusions are rare, so precision will be low in absolute terms. Lift over the baseline rate is the fairer measure.

## Suggested split

- **Pipeline:** downloads, cleaning, GitHub Actions, refresh setup
- **Modeling:** features, model tuning (try DBSCAN or an autoencoder as a comparison), validation
- **Dashboards:** one person each, Power BI as the executive summary, Tableau as the exploration view
