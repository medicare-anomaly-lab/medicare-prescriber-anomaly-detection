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

### Prescribers across years
- 46,764 unique NPIs total. **31,859 (68%) appear in all 3 years**, 6,985 in 2 years, 7,920 in only 1.
- **Decision: keep prescribers who appear in at least 2 of the 3 years (Option B).** Why:
  - Two years is enough to measure change, and a sudden spike is one of the most suspicious patterns.
  - Keeps newer prescribers (lots of NPs and PAs started in 2020), the fastest-growing group.
  - Doesn't filter out short-lived patterns: someone who prescribes heavily for two years then disappears stays in.
  - 1-year prescribers dropped: a single year is too noisy and has no trend.
- **Robustness check planned:** rerun the model keeping only prescribers in all 3 years (Option A) and compare lift. If results are similar, the finding doesn't depend on this choice.

### Specialty mix
- Top 5 every year: Nurse Practitioner, Physician Assistant, Dentist, Family Practice, Internal Medicine.
- **NPs grew 15% (5,943 to 6,840) and PAs 10% (5,571 to 6,117) from 2019 to 2021.** That explains most of the growth in total prescribers.
- Dentists are the 3rd biggest group, worth a look since dentists prescribe opioids after extractions.
- The top 5 stays the same every year, so averaging across 2019 to 2021 is safe in terms of specialty mix.
- **Why we compare within specialty:** each specialty has its own normal (dentist vs family doctor vs neurosurgeon). Pooling everyone would just flag high-prescribing specialties instead of odd individuals.
- **Limitation: "Nurse Practitioner" is a messy peer group.** CMS lumps all NPs together, but a psychiatric NP, a primary care NP, and a hospital NP prescribe very differently. Some NPs may look unusual just because their setting differs from most NPs. Same likely applies to PAs. Watch for this when reviewing who gets flagged, and mention it in the writeup.

### Opioid prescribing dropped a lot
- Median opioid rate: **2019: 2.22% | 2020: 1.59% | 2021: 1.24%**, about a 44% drop in two years.
- Why it dropped: NC STOP Act (2017) limiting first-time opioid prescriptions and requiring checks of the state monitoring database, CDC opioid guidelines (2016), fewer elective surgeries and dental visits during COVID (2020), and more NPs and PAs, who tend to prescribe fewer opioids.
- We used the **median** instead of the mean because the data is skewed. A few prescribers at 60 to 90% would drag the mean up.
- **Big implication for features:** a 3% rate means something different in 2019 (a bit above typical) than in 2021 (more than double typical). Don't just average raw rates across years. Compare each prescriber to peers in the **same specialty and same year** first, then average those comparisons.
- **Feature idea: "against the trend."** If almost everyone's opioid rate dropped and a prescriber's went up, that's a strong signal.

### Missing values
- Most of the "most missing" columns are **suppression flags** (`_Sprsn_Flag`). Those are blank when nothing was hidden, so high missingness there is actually good news (e.g. `Gnrc_Sprsn_Flag` is 98% blank, generic claims are almost never hidden).
- `Opioid_LA_Prscrbr_Rate` is 67% blank: mostly prescribers with no opioids at all (can't compute a share of zero) plus suppressed small counts.
- Patient race and older age-group counts are 60 to 70% blank due to suppression, one more reason not to use race as a feature.
- `Prscrbr_St2` (address line 2) is 77% blank, irrelevant.
- **What a blank means depends on the column.** A blank can mean (1) nothing to report (a blank suppression flag = nothing hidden), (2) doesn't apply (long-acting opioid rate when there are no opioids), or (3) a hidden small number (1 to 10). This is "missing not at random": the blank itself carries information, so don't blindly fill with 0 or drop rows.
- **Every number has a "buddy" flag column.** Example: a dentist with `Brnd_Tot_Clms` blank and `Brnd_Sprsn_Flag` = `*` (1 to 10 brand prescriptions, hidden), but `Gnrc_Tot_Clms` = 74 with a blank flag (real number shown). A blank flag is the normal case.

### Missingness in the columns we'll actually use
| Column | Blank |
|---|---|
| Brnd_Tot_Clms | 42% |
| Opioid_LA_Tot_Clms | 37% |
| Opioid_Tot_Clms / Opioid_Prscrbr_Rate | 29% (same rows, rate is computed from count) |
| Antbtc_Tot_Clms | 27% |
| Tot_Benes | 8% (fewer than 11 patients) |
| Bene_Avg_Risk_Scre | ~0% (1 row) |
| Tot_Clms, Tot_Drug_Cst, Tot_Day_Suply | 0% |

- **Verified that blank opioid counts mean "1 to 10, hidden," not "none":** 30% of rows have exactly 0 opioids (zeros are reported as 0), and a separate 29% are blank. Blank-opioid prescribers have a median of 130 total claims vs 255 overall: smaller practices, but real ones writing a handful of opioid prescriptions.
- **The three opioid groups:** 30% wrote exactly 0 (shown as 0), 29% wrote 1 to 10 (hidden, blank), 41% wrote 11 or more (real count shown). So 70% wrote at least one. Filling blanks with 0 would wrongly say 59% wrote none.
- **Why it matters:** a hidden 1 to 10 barely moves the rate for a prescriber with 5,000 claims (0.02% to 0.2%) but swings it a lot for one with 60 claims (1.7% to 17%). The 50-claim cutoff removes most of the extreme cases.
- **Decision: fill hidden counts with 5 and add a "was hidden" yes/no column** (e.g. `opioid_hidden`). Why:
  - 0 would wrongly lump the 1-to-10 group in with prescribers who wrote none.
  - 5 is the midpoint of 1 to 10, the most reasonable single guess.
  - The yes/no column tells the model which values are estimates instead of hiding that.
  - Apply the same rule to every count column CMS suppresses (brand, opioid, long-acting opioid, antibiotic, patients). Only fill when the value is truly hidden, not when it doesn't apply (e.g. long-acting opioid rate when there are 0 opioids should be 0).

### Tiny prescribers
- **19% of rows have fewer than 50 claims.** A minimum claims cutoff (e.g. 50) drops about a fifth of rows, but those percentages are too noisy to trust.
- Example of the noise: a prescriber with 14 claims and 3 opioids shows a 21% rate. One patient can flip the whole percentage.
- **Decision: drop prescriber-years with fewer than 50 total claims.** Apply this per year first, then apply the 2-of-3-years rule to what's left.

#### Chart evidence: how much we don't know when counts are hidden
For prescribers with a hidden opioid count (true value 1 to 10), the possible opioid rate range for the median prescriber in each volume group:

| Total claims | Hidden prescriber-years | Possible opioid rate |
|---|---|---|
| Under 50 | 8,837 | 3.7% to 37.0% |
| 50-99 | 5,784 | 1.4% to 14.1% |
| 100-249 | 7,253 | 0.6% to 6.5% |
| 250-999 | 7,612 | 0.2% to 2.3% |
| 1,000+ | 4,308 | 0.1% to 0.5% |

- Under 50 claims, we can't tell a prescriber at 4% from one at 37%. The range shrinks fast above 50.
- About 65% of under-50 rows (8,837 of 13,512) have a hidden opioid count, so most of that group is guesswork.
- **Honest caveat:** the 50-99 group is still fairly wide (1.4% to 14.1%). The cutoff reduces the problem but doesn't remove it. That's why we also keep the "hidden" yes/no column, and why the 100-claim robustness check matters.

#### Lesson: suppression can quietly skew charts
Our first version of this chart showed the share of prescribers with an opioid rate over 20% by volume, and small prescribers looked *least* extreme (Under 50: 12.0%, 50-99: 29.6%, 100-249: 27.7%, 250-999: 17.5%, 1,000+: 6.5%). That was an artifact: the chart dropped blank (hidden) rates. A prescriber with 30 claims needs 11+ opioid prescriptions before CMS shows the count (already 37%), so among small prescribers we only see 0% or very high rates, and everyone in between disappears. The visible under-50 group was mostly zeros. Takeaway: always ask which rows a chart silently drops.

#### Why we chose 50
1. **Stable percentages.** At 50+ claims, one extra prescription moves a rate by at most 2 points. At 14 claims it moves it by 7 points, and 3 prescriptions for one patient can look like a 21% opioid rate. Below 50, percentages mostly reflect chance, not prescribing habits.
2. **Hidden counts matter less.** Our fill-with-5 rule for hidden 1 to 10 counts can be off by up to 4 or 5 prescriptions. At 50+ claims that's a small error; for tiny prescribers it can change the rate by 30+ points.
3. **Fewer false alarms.** Without a cutoff, the model would flag tiny prescribers just because their numbers bounce around, burying the real cases.
4. **It follows published research on the same data and prescriber types** (below), and sits between the CMS privacy floor (11) and the threshold OIG used in its own review (100).
5. **Little fraud risk lost.** Prescribing fraud worth investigating usually involves high volume. We'll verify this in Step 4 (see check below).

#### Research that used 50
- **Lozada, Raji, Goodwin, Kuo et al. (2020).** "Opioid Prescribing by Primary Care Providers: a Cross-Sectional Analysis of Nurse Practitioner, Physician Assistant, and Physician Prescribing Patterns." *Journal of General Internal Medicine*, 35(9), 2584-2592. ([link](https://link.springer.com/article/10.1007/s11606-020-05823-0))
  - What they did: compared opioid prescribing by NPs, PAs, and physicians using Medicare Part D data. Methods: "We selected primary care providers who prescribed at least 50 prescriptions."
  - **Why they used it:** the paper doesn't spell out a reason for 50. The goal is implied: keep prescribers with enough volume that their prescribing rates are meaningful. They acknowledged the tradeoff in their limitations: the cutoff excluded 26% of MDs, 48% of NPs, and 53% of PAs, so "we cannot generalize our findings to those who prescribed less often."
  - **Why it's the best match for us:** same data (Part D), same focus (opioids), same prescriber types (NPs, PAs, physicians).
  - **Takeaway for us:** they lost a lot of NPs and PAs with this cutoff. We should check how many NPs and PAs our cutoff drops and mention it as a limitation, same as they did. Our findings won't apply to very low-volume prescribers.

#### Other cutoffs used on this data (for context)
- **11 claims:** the floor CMS sets itself, records from 10 or fewer claims are excluded for privacy. The CDC's 2019 antibiotic prescriber study kept prescribers with 11+ antibiotic prescriptions. ([CMS methodology](https://data.cms.gov/sites/default/files/2023-05/MUP_DPR_RY23_20230424_Methodology_508.pdf), [CDC MMWR](https://www.cdc.gov/mmwr/volumes/71/wr/mm7106a3.htm))
- **100 records:** HHS-OIG's 2012 report on questionable Part D prescribing only analyzed general-care physicians with 100+ prescription records totaling $100,000+, and 100+ records for Schedule II/III analyses, focusing their review on high-volume, high-dollar prescribers. ([OIG OEI-02-09-00603](https://oig.hhs.gov/oei/reports/oei-02-09-00603.pdf))

#### Suggested writeup sentence
"We excluded prescriber-years with fewer than 50 claims, following Lozada et al. (2020), who used the same threshold in a Part D study of opioid prescribing by NPs, PAs, and physicians. Below this level, a single prescription shifts a prescriber's rates by several percentage points, making comparisons unreliable. This threshold sits between the CMS suppression floor (11 claims) and the threshold used in HHS-OIG's review of questionable Part D prescribing (100 records). Our findings therefore do not apply to very low-volume prescribers."

- **To do:** check how many NPs and PAs the 50-claim cutoff drops, and report it as a limitation.
- **Robustness check planned:** rerun with cutoffs of 11 and 100 and compare lift.
- **Note: the LEIE has no claims cutoff.** People are excluded for legal reasons (convictions, license loss, etc.), regardless of prescribing volume. OIG's 100-record threshold came from a separate 2012 analytic report, not the exclusion rules, so there's no "their cutoff" to match.
- **Check in Step 4:** after matching to the LEIE, count how many excluded prescribers fall under 11, 50, and 100 claims. If 50 drops a meaningful share of them, lower the cutoff. This shows the cutoff doesn't throw away the people we're trying to find.
- **Support for our fill-with-5 decision:** Herland, Khoshgoftaar and Bauder's Medicare fraud detection study (Journal of Big Data, 2018) also imputed 5 for suppressed counts below 11. ([J Big Data](https://link.springer.com/article/10.1186/s40537-018-0138-3)) The CDC study imputed 10 instead, as a conservative choice.

### Opioid rate within Family Practice (histogram)
- Strongly right-skewed: most prescribers are under 10%, a small tail stretches out to 60 to 90%.
- A family practice prescriber at 60%+ is far from their peers, these are the kind of cases the model should surface.
- Because the data is so skewed, regular z-scores (mean and standard deviation) get pulled around by outliers. Robust z-scores (median and MAD) or log transforms will work better.
- Note: `.hist()` silently skips blanks, so the ~1/3 of prescribers with hidden 1-to-10 opioid counts aren't in this plot.

#### Family Practice by year (same buckets, side by side)
- Median opioid rate: **2019: 2.7% | 2020: 2.4% | 2021: 2.2%**, about a 19% drop.
- **Interesting:** that's much smaller than the 44% drop across all prescribers (#3). So the overall drop isn't just doctors prescribing fewer opioids. A big part is the **mix changing**: more NPs and PAs (who prescribe fewer opioids) entering the data. Good presentation point: an overall trend can partly come from who's in the group, not just behavior change.
- The spike at 0 to 0.5% grows each year (about 440 to 480 to 540): more family doctors prescribing almost no opioids.
- The tail past 10% stays thin and similar each year. The extreme prescribers don't disappear.
- **Plotting lesson:** when comparing groups, use the same bins for all of them and side-by-side panels with a shared y-axis. Overlaid see-through histograms with separate bins were unreadable.

## Step 1 complete
All exploration done. Next: Step 2, turn these findings into features.



## Step 2: Features (decisions so far)

Each feature is compared to peers in the same specialty and same year (robust z-score), then averaged across a prescriber's years.

### A. How much they prescribe (all kept)
1. **Prescription volume** `log(Tot_Clms)`: "pill mill" practices write far more prescriptions than peers. Log because volume is very skewed.
2. **Prescriptions per patient** `Tot_Clms / Tot_Benes`: many prescriptions per patient can mean overprescribing or billing for drugs patients don't need.
3. **Total drug cost** `log(Tot_Drug_Cst)`: fraud is about money.
- **Overlap to test later:** volume and total cost likely move together. Check correlation (above ~0.9 = mostly redundant) and run the model with and without one.

### B. What kind of drugs (all kept)
4. **Cost per prescription** `Tot_Drug_Cst / Tot_Clms`: steering patients to expensive drugs can point to kickbacks.
5. **Brand-name share** `Brnd_Tot_Clms / Tot_Clms`: kickback schemes usually push brand-name drugs.
6. **Days supply per prescription** `Tot_Day_Suply / Tot_Clms`: unusually long supplies can mean more pills going out than patients need.
- **Overlap to test later:** brand share and cost per prescription overlap but catch different things. Cost can be high for legit reasons: sicker patients, or specialty drugs (cancer, HIV, MS, hepatitis C) that are expensive even as generics. Comparing within specialty handles some of this (oncologists only vs oncologists), and the risk score covers patient sickness.

### C. Opioids (first four all kept)
7. **Opioid rate** `Opioid_Tot_Clms / Tot_Clms` (filled counts, recomputed): classic diversion signal.
8. **Share of patients on opioids** `Opioid_Tot_Benes / Tot_Benes`: #7 counts prescriptions, this counts people. A few patients with many refills vs many patients each getting opioids are different patterns.
9. **Long-acting opioid share** `Opioid_LA_Tot_Clms / Opioid_Tot_Clms`: long-acting opioids carry higher overdose and diversion risk. 0 when there are no opioids (doesn't apply), not 5.
10. **Opioid days per prescription** `Opioid_Tot_Suply / Opioid_Tot_Clms`: the NC STOP Act limits first-time opioid prescriptions to 5 to 7 days.

#### Why we weight opioids heavily on purpose
Four of our features are about opioids, so the model gives opioid patterns extra weight. This is a deliberate choice. Writeup sentence: "We intentionally included four opioid features because opioid diversion is a major focus of prescribing fraud enforcement."

Evidence:
- **HHS-OIG has tracked questionable opioid prescribing in Part D every year.** In 2019 (inside our training window), OIG identified 142 prescribers with questionable opioid prescribing, defined as ordering opioids for the highest numbers of patients at serious risk of misuse or overdose (more than 3 standard deviations above the mean, top 0.3%). They ordered 74,820 opioid prescriptions costing Part D $22.1 million. About a third were NPs or PAs. ([OIG OEI-02-20-00320, Aug 2020](https://oig.hhs.gov/oei/reports/OEI-02-20-00320.pdf))
  - The count dropped from 401 (2016) to 282 (2017) to 198 (2018) to 142 (2019), matching the downward opioid trend we saw in NC.
  - The fact that a third were NPs or PAs supports keeping those prescriber types in our data.
- **OIG's earlier report** found about 400 prescribers in 2016 with questionable opioid prescribing for patients at serious risk, patterns "far outside the norm" that "warrant further scrutiny." ([OIG OEI-02-17-00250, Jul 2017](https://oig.hhs.gov/reports/all/2017/opioids-in-medicare-part-d-concerns-about-extreme-use-and-questionable-prescribing/))
- **Opioid diversion is a standing category in DOJ's yearly National Health Care Fraud Takedown.** The June 2026 takedown charged 36 defendants, including 28 licensed medical professionals, over illegal diversion of prescription opioids and other controlled substances. ([DOJ, Jun 2026](https://www.justice.gov/opa/pr/national-health-care-fraud-takedown-results-455-defendants-charged-connection-over-65))
- **OIG's method is similar to ours:** they flag prescribers far above the norm (3+ standard deviations). We do the same idea but within specialty and with robust z-scores.

#### Check after modeling
Look at each flagged prescriber's top reasons. If nearly every flag is opioid-driven, the model is effectively an opioid detector, mention that in the writeup. A mix of reasons (cost, brand share, opioids) means the other features matter too.

### C (continued). Other drug classes (both kept for now)
11. **Antipsychotics in patients 65+** `Antpsyct_GE65_Tot_Clms / GE65_Tot_Clms`: antipsychotics are sometimes overused in older adults, especially nursing home residents with dementia, to sedate rather than treat a real need. Adds a non-opioid kind of signal. Mostly 0 for prescribers with few older patients.
   - Evidence: OIG found slightly over half of Medicare-paid antipsychotic claims for elderly nursing home residents should not have been covered (unaccepted uses or no documentation), and 88% were for patients with dementia, a group the FDA warns faces higher risk of death from these drugs. ([OIG news release, Jun 2011, report OEI-07-08-00150](https://oig.hhs.gov/newsroom/news-releases-articles/overmedication-nursing-home-patients-troubling/))
   - A later OIG report found about 80% of long-stay nursing home residents were prescribed a psychotropic drug (2011-2019), and that Part D claims lack diagnosis codes, limiting oversight. ([OIG, Long-Term Trends of Psychotropic Drug Use in Nursing Homes](https://oig.hhs.gov/reports/all/long-term-trends-of-psychotropic-drug-use-in-nursing-homes))
12. **Antibiotic rate** `Antbtc_Tot_Clms / Tot_Clms`: more of a care-quality issue than fraud, but kept for now.
   - **Our hypothesis ("careless prescriber"):** a prescriber who overprescribes in one area may overprescribe across the board, not just opioids. If that's true, antibiotic rate should correlate with opioid rate and help the model.
   - **Test:** check the correlation between the antibiotic and opioid z-scores, and use SHAP after modeling to see how much the model actually relies on #11 and #12. If they contribute nothing, drop them.

#### Feature importance plan
- Use **SHAP** to see which features drive each prescriber's anomaly score. SHAP's TreeExplainer works with scikit-learn's Isolation Forest.
- Use it to answer: are volume and total cost redundant? Do brand share and cost per prescription both matter? Do antipsychotics and antibiotics add anything? Is the model mostly an opioid detector?

### D. Change over time (both kept)
13. **"Against the trend" (opioids):** opioid-rate z-score in last year minus first year. Almost everyone cut back on opioids 2019 to 2021, so someone rising relative to peers is moving opposite to everyone else.
14. **Volume growth:** volume z-score in last year minus first year. A sudden jump relative to peers is a common pattern when a scheme starts.
- Use **z-score changes, not raw changes**, because everyone's opioid rate dropped. A raw drop could still mean cutting back slower than peers.
- Prescribers with only 2 years (Option B) get last minus first of the two years they have, a smaller window.
- **Limitation, legit reasons for a jump:** finishing residency or ramping up a new practice, taking over a retiring doctor's patients, going from part-time to full-time, or shifting into hospice/palliative care or pain management (more opioids, for good reason). Some flagged "growth" will be career changes, not fraud.

### E. Patient mix: adjust with regression (Way 2)
These describe who the patients are, not what the prescriber did. Goal: don't flag a prescriber just for treating sicker or older patients.

**Decision: regression adjustment.** For each behavior feature (1 to 12), within each specialty and year:
1. Fit a **robust regression**: feature ~ patient risk score + average patient age.
2. Take each prescriber's **residual** (actual minus expected given their patients).
3. Turn residuals into **robust z-scores** (median and MAD) within that specialty-year.
4. Average each prescriber's z-scores across their years. The change features (13, 14) are built from these adjusted z-scores, so they're adjusted too.

Each feature then means: "how far above what we'd expect for a prescriber with patients this sick and this old?"

**What goes in the regression:**
- **Risk score** (`Bene_Avg_Risk_Scre`): yes, medical need.
- **Average patient age** (`Bene_Avg_Age`): yes, older patients take more medications (partly captured by risk score already).
- **Low-income share** (`LIS_Tot_Clms / Tot_Clms`): **no, explanation only.** Some fraud schemes deliberately recruit Medicare and Medicaid beneficiaries for prescriptions they don't need. Adjusting for low-income share could hide those schemes. OIG testimony describes "recruiters" who target drug-seeking patients and "offer them money for the use of their Medicare or Medicaid numbers," and pharmacies "paying patients with cash or narcotics to fill illegitimate and expensive prescriptions." ([OIG Senate testimony, Cantrell and Wright, Jun 2013](https://www.oig.hhs.gov/documents/testimony/133/20130624_-_Cantrell.pdf)) Note: the testimony is about Medicare/Medicaid beneficiaries generally, not low-income share specifically, so frame this as a precaution, not a proven pattern.

- **Rural vs urban** (`Prscrbr_RUCA`): **yes, added.** Rural prescribers often see sicker patients with less access to specialists, so a rural family doctor may handle things an urban one would refer out. Encode as metro (RUCA 1 to 3) vs non-metro (RUCA 4 to 10), following the standard USDA RUCA groupings. Check how many prescribers have a missing RUCA code before fitting.

**Chart evidence for adjusting by risk score** (prescribers with 50+ claims, median by patient risk group):

| Risk group | Prescriptions per patient | Cost per prescription |
|---|---|---|
| Healthier (under 1) | 2.8 | $55 |
| Average (1 to 1.5) | 3.9 | $68 |
| Sicker (1.5 to 2.5) | 4.0 | $77 |
| Much sicker (2.5+) | 4.0 | $79 |

- Sicker patients get about 40% more prescriptions and about 40% pricier ones. Most of the jump is from healthier to average, then it levels off.
- Without adjusting, the model would flag prescribers just for having sick patients.
- Note: an earlier hexbin version (risk score vs cost per prescription, log scale) looked almost flat and was hard to read. The grouped bar version is clearer and shows both effects.

**Chart evidence for adding rural/urban** (median opioid rate, all prescribers, raw data):

| Year | Metro (RUCA 1-3) | Non-metro (RUCA 4-10) | Non-metro vs metro |
|---|---|---|---|
| 2019 | 2.1% | 2.7% | 1.3x |
| 2020 | 1.4% | 2.2% | 1.6x |
| 2021 | 1.0% | 1.9% | 1.9x |

- Non-metro prescribers have a higher median opioid rate every year.
- The gap is growing: metro dropped about 50% from 2019 to 2021, non-metro only about 30%.
- **Caveat:** this doesn't separate specialty mix. Rural areas likely have more primary care and fewer specialists, which could explain part of the gap. That's exactly why rural/urban goes into the regression within each specialty-year instead of being judged from this chart alone.

**Example of why low-income share stays out of the adjustment:** two family doctors with equally sick patients (risk score 1.3). Doctor A: 20% low-income patients, 3% opioid rate. Doctor B: 90% low-income patients, 25% opioid rate. Without adjusting for low-income share, B is a huge outlier and gets flagged. If we adjusted for it, the regression would learn "low-income-heavy practices prescribe more," expect maybe 15% for B, and B might not get flagged. That would excuse the exact pattern a patient-recruiting scheme would create. Risk score is different: it comes from diagnoses, so it reflects real medical need. Low income by itself is not a medical need. Use low-income share after flagging, to explain results ("flagged, 90% low-income patients, patients not sicker than average").

**Final regression:** feature ~ risk score + average patient age + rural/urban

**Why Way 2 over risk tiers (Way 1):** smoother and more precise, no arbitrary cutoff, doesn't halve peer groups. Presenting to a technical audience.

**Technical details:**
- **Use robust regression (`HuberRegressor`), not OLS.** OLS gets pulled toward outliers, and outliers are who we're looking for. Extreme prescribers could tilt the line toward themselves and hide.
- **Small groups:** specialties with fewer than ~30 prescribers in a year get pooled into "Other" before fitting.
- **Check it worked:** after adjusting, features should have ~0 correlation with risk score and age. Good slide.
- **Robustness check:** compare against Way 1 (specialty x year x risk tier above/below median) later.
