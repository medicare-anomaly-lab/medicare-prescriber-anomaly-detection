# Project log

Running notes on decisions, findings, and open questions. Add to this as we go, it becomes the backbone of the writeup.

## Setup decisions

- **Tools:** Databricks Free Edition (UNCW account) for exploring and modeling. Repo connected as a Git folder. Databricks can reach both data.cms.gov and oig.hhs.gov (tested Nov 1, both returned 200), so downloads can run from Databricks too.
- **Storage:** raw CSVs in the volume `/Volumes/workspace/default/raw/`. NC-only tables saved as `workspace.default.partd_nc_2019`, `_2020`, `_2021`.
- **Training years: 2019 to 2021.** Why:
  - Exclusions take years to happen (investigation, charges, conviction). Training on older years leaves 2022 to 2026 for exclusions to show up.
  - Three years smooths out one-off years (like 2020 with COVID) and lets us measure trends like growth.
  - Older years (2013 to 2018) skipped because opioid guidelines changed a lot, and the LEIE drops people who were later reinstated, so older data has more missing answers.
  - Idea if time allows: backtest a second window (train 2016 to 2018, check exclusions 2019+) to show the result isn't luck.
- **Starting with NC only** to keep things fast. Can scale to the whole country later.
- **Dashboard:** only one (Power BI or Tableau), per assignment rules. Tool not picked yet.

## Bugs found

- **CMS changed its catalog format.** Each year is now its own dataset with the year in the title (for example `Medicare Part D Prescribers - by Provider : 2021-12-03`), and the dates in the titles aren't consistent. `src/download.py` still searches for the old title without a year, which is probably why the first GitHub Actions run failed. Fix in Step 5.

## EDA findings (Step 1)

### Size
- NC prescribers per year: 2019: 38,147 | 2020: 38,988 | 2021: 40,332. Combined about 117k rows, 85 columns.
- Count grows each year. Open question: why? More nurse practitioners and PAs prescribing?

### Suppressed values (important for features)
- CMS hides counts between 1 and 10 for patient privacy.
- `*` in a `_Sprsn_Flag` column = value hidden because it was 1 to 10.
- `#` = value hidden so the small number can't be back-calculated from totals.
- **Blank (NaN) is not the same as 0.** 0 means none prescribed. Blank means some were prescribed (1 to 10), exact number unknown.
  - Example: a Family Practice prescriber with 151 opioid claims had blank long-acting opioid columns, meaning 1 to 10 long-acting prescriptions.
- **Decision needed:** how to treat suppressed values (0, 5 as the midpoint, or a separate "suppressed" flag). Pick one and explain why.

### Useful columns
- `Opioid_Prscrbr_Rate` and `Opioid_LA_Prscrbr_Rate`: CMS already computes opioid share as a percent.
- `Prscrbr_RUCA`: rural vs urban (1 = metro core, higher = more rural). Useful for peer groups and maps.
- `Prscrbr_Ent_Cd`: I = individual, O = organization. Probably keep individuals only.
- `Bene_Avg_Risk_Scre`: how sick a prescriber's patients are on average.
- `LIS_Tot_Clms`, `Bene_Dual_Cnt`: low-income and dual-eligible (Medicare + Medicaid) patients.
- `Prscrbr_Crdntls` is messy free text (MD vs M.D., N.P., ACNP). Use `Prscrbr_Type` for specialty instead.

### Unusual is not the same as suspicious
- **Specialty matters.** A neurosurgeon had a 61% opioid rate, which is extreme overall but likely normal for spine surgery patients. Compare doctors within their own specialty.
- **Patient mix matters.** A nurse practitioner whose patients were all low-income and dual-eligible had a cost per prescription of about $165, vs about $72 for a typical family practice prescriber. Their patients' risk score was 2.0 (most are around 1.1 to 1.3). Likely a sicker, more complex population, not fraud. Including risk score or patient mix keeps the model from flagging doctors just for treating sick or poor patients.
- **Tiny prescribers are noisy.** An ER doctor with 14 claims: one opioid prescription would be 7%. Need a minimum claims cutoff.

### Ethics
- Patient demographic columns exist (race, sex, dual status). Don't use race as a model feature: a doctor shouldn't be flagged as unusual because of who their patients are.
- Being statistically unusual is not evidence of wrongdoing. Don't publish flagged doctors by name (the pipeline hashes IDs).

## Still to explore (Step 1)

- [ ] How many prescribers appear in all 3 years vs only 1 or 2
- [ ] Top specialties by year, did the mix change
- [ ] Median opioid rate by year, is it dropping
- [ ] Which columns are mostly blank
- [ ] Share of prescribers under 50 claims
- [ ] Histogram of opioid rate within one specialty, any extreme outliers
