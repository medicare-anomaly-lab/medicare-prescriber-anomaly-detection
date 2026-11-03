# Step 2: Feature brainstorm (draft)

A starting list for us to go through together. For each one, mark **Keep / Drop / Change** in the last column and add a note if we disagree. Aim to end with roughly 10 to 15 features, enough to catch different kinds of unusual, few enough that we can explain every one.

## Ground rules (from Step 1)

1. **Clean first:** drop prescriber-years under 50 claims, keep prescribers with at least 2 of 3 years left, individuals only (`Prscrbr_Ent_Cd == "I"`).
2. **Hidden counts:** fill hidden 1-to-10 counts with 5 and keep a yes/no "hidden" column. Recompute rates ourselves from the filled counts instead of using CMS's blank rate columns.
3. **Compare within specialty and year:** every feature gets turned into a robust z-score (distance from the median, divided by the MAD) among prescribers with the **same specialty in the same year**. Then average each prescriber's z-scores across their years.
4. **No race or sex features.** A prescriber shouldn't look unusual because of who their patients are.

## A. How much they prescribe

| # | Feature | How to calculate | Why it could signal a problem | Keep / Drop / Change |
|---|---|---|---|---|
| 1 | Prescription volume | `log(Tot_Clms)` | "Pill mill" style practices write far more prescriptions than peers. Log because volume is extremely skewed. | |
| 2 | Prescriptions per patient | `Tot_Clms / Tot_Benes` | Lots of prescriptions and refills per patient can mean overprescribing or billing for drugs patients don't need. | |
| 3 | Total drug cost | `log(Tot_Drug_Cst)` | Fraud is about money, so prescribers driving unusually high spending relative to peers are worth a look. | |

## B. What kind of drugs

| # | Feature | How to calculate | Why it could signal a problem | Keep / Drop / Change |
|---|---|---|---|---|
| 4 | Cost per prescription | `Tot_Drug_Cst / Tot_Clms` | Steering patients to expensive drugs can point to kickbacks from drug makers or pharmacies. | |
| 5 | Brand-name share | `Brnd_Tot_Clms / Tot_Clms` | Kickback schemes usually push brand-name drugs, since generics have little profit in them. | |
| 6 | Days supply per prescription | `Tot_Day_Suply / Tot_Clms` | Unusually long supplies per prescription can mean larger quantities going out the door than patients need. | |

## C. Opioids and other controlled drugs

| # | Feature | How to calculate | Why it could signal a problem | Keep / Drop / Change |
|---|---|---|---|---|
| 7 | Opioid rate | `Opioid_Tot_Clms / Tot_Clms` (filled counts) | The classic diversion signal: opioids making up much more of a practice than peers in the same specialty. | |
| 8 | Share of patients on opioids | `Opioid_Tot_Benes / Tot_Benes` | Catches prescribers who put a large share of their patients on opioids, not just a few patients with lots of refills. | |
| 9 | Long-acting opioid share | `Opioid_LA_Tot_Clms / Opioid_Tot_Clms` (0 if no opioids) | Long-acting opioids (like OxyContin) carry higher overdose and diversion risk. Doesn't apply when there are no opioids, so 0 there, not 5. | |
| 10 | Opioid days per prescription | `Opioid_Tot_Suply / Opioid_Tot_Clms` (0 if no opioids) | Big opioid supplies per prescription go against the NC STOP Act's short-prescription limits. | |
| 11 | Antipsychotics in patients 65+ | `Antpsyct_GE65_Tot_Clms / GE65_Tot_Clms` | OIG has flagged overuse of antipsychotics in older adults (especially in nursing homes) as a known problem area. | |
| 12 | Antibiotic rate | `Antbtc_Tot_Clms / Tot_Clms` | Overprescribing, but it's more of a quality issue than fraud. **Probably drop**, or keep only to show the model isn't just an opioid detector. | |

## D. Change over time

| # | Feature | How to calculate | Why it could signal a problem | Keep / Drop / Change |
|---|---|---|---|---|
| 13 | "Against the trend" (opioids) | Opioid rate z-score in their last year minus their first year | Almost everyone cut back on opioids from 2019 to 2021. Someone who went the other way relative to peers stands out. | |
| 14 | Volume growth | `log(Tot_Clms)` z-score in last year minus first year | A sudden jump in prescribing is a common pattern when a scheme starts. | |

## E. Patient mix (context, not red flags)

These describe **who the patients are**, not what the prescriber did. They're here so the model doesn't flag someone just for treating sicker or poorer patients. We need to decide how to use them (see open questions).

| # | Feature | How to calculate | Why include it | Keep / Drop / Change |
|---|---|---|---|---|
| 15 | Patient risk score | `Bene_Avg_Risk_Scre` | Sicker patients need more and pricier drugs. High cost + high risk score is less suspicious than high cost + healthy patients. | |
| 16 | Average patient age | `Bene_Avg_Age` | Older patients take more drugs. Gives context for volume. | |
| 17 | Low-income share | `LIS_Tot_Clms / Tot_Clms` | Low-income and dual-eligible patients tend to be sicker. Same context role as risk score. Careful: we don't want "treats poor patients" to look suspicious. | |

## Not features, but used for grouping or filtering

| Column | How we use it |
|---|---|
| `Prscrbr_Type` (specialty) | Peer group for the z-scores. Small specialties (under ~30 prescribers) get pooled into "Other". |
| `year` | Peer group for the z-scores (compare within the same year). |
| `Prscrbr_Ent_Cd` | Keep individuals (`I`) only. |
| `Prscrbr_RUCA` (rural vs urban) | Option to split peer groups further, or just use for dashboard maps. |
| Hidden yes/no columns | Track which values are estimates. **Probably don't feed these into the model**, or it might flag prescribers just for having hidden counts. Use them to check results instead. |

## Leaving out on purpose

- **Patient race and sex counts:** fairness (see project log), and mostly hidden anyway.
- **Credentials (`Prscrbr_Crdntls`):** messy free text, specialty covers it.
- **Address, city, ZIP:** not prescribing behavior. ZIP/RUCA can go on the dashboard map.
- **65+ and Medicare Advantage vs standalone plan breakdowns:** mostly repeat the totals.

## Open questions to decide together

1. **How do we use the patient-mix features (E)?** Options:
   - (a) Feed them in like any other feature. Simple, but then an unusual patient mix alone can get someone flagged.
   - (b) Use them only to explain results ("flagged, but their patients are very sick").
   - (c) Adjust for them, e.g. compare prescribers to peers with similar risk scores. More work, most fair.
2. **Do we drop the antibiotic rate (#12)?**
3. **How many features?** If several are basically measuring the same thing (e.g. #7 and #8), keeping both gives opioids extra weight in the model. Check how correlated they are first.
4. **Rural vs urban:** split peer groups by it, or not? Rural prescribers may see sicker patients with less access to specialists.
5. **Specialty pooling:** what's the minimum group size before a specialty gets lumped into "Other"?
