"""
Fake data in the same shape as the real files, so you can test the pipeline in seconds.
It plants a few "weird" prescribers and makes some of them show up on a fake exclusions list,
so if the pipeline works, the lift numbers should come out well above 1.
"""
import numpy as np
import pandas as pd

SPECIALTIES = {"Family Practice": 0.08, "Internal Medicine": 0.06, "Nurse Practitioner": 0.07,
               "Pain Management": 0.35, "Psychiatry": 0.02, "Cardiology": 0.01, "Dentist": 0.15}


def make_sample(cfg, n=4000, seed=7):
    rng = np.random.default_rng(seed)
    raw = cfg["data"]["raw_dir"]
    state = cfg["data"].get("dev_state") or "NC"
    years = cfg["model"]["train_years"]

    npis = [str(1000000000 + i) for i in range(n)]
    specs = rng.choice(list(SPECIALTIES), n)
    lasts = [f"LAST{i}" for i in range(n)]
    firsts = [f"FIRST{i}" for i in range(n)]
    weird = rng.random(n) < 0.02  # 2% planted anomalies

    for y in years:
        claims = rng.lognormal(6, 0.8, n) * np.where(weird, rng.uniform(3, 8, n), 1)
        benes = claims / rng.uniform(4, 8, n) / np.where(weird, 3, 1)
        base_op = np.array([SPECIALTIES[s] for s in specs])
        opioid = claims * np.clip(base_op * rng.uniform(0.7, 1.3, n) * np.where(weird, 3, 1), 0, 0.95)
        df = pd.DataFrame({
            "Prscrbr_NPI": npis, "Prscrbr_Last_Org_Name": lasts, "Prscrbr_First_Name": firsts,
            "Prscrbr_State_Abrvtn": state, "Prscrbr_Type": specs,
            "Tot_Clms": claims.round(), "Tot_30day_Fills": (claims * 1.2).round(),
            "Tot_Drug_Cst": claims * rng.uniform(30, 90, n) * np.where(weird, 2.5, 1),
            "Tot_Day_Suply": claims * rng.uniform(20, 35, n), "Tot_Benes": benes.round(),
            "Brnd_Tot_Clms": claims * rng.uniform(0.1, 0.3, n) * np.where(weird, 2.5, 1),
            "Gnrc_Tot_Clms": claims * 0.7, "Opioid_Tot_Clms": opioid.round(),
            "Opioid_LA_Tot_Clms": opioid * rng.uniform(0.05, 0.2, n) * np.where(weird, 3, 1),
            "Antbtc_Tot_Clms": claims * rng.uniform(0.02, 0.08, n), "Antpsyct_GE65_Tot_Clms": claims * 0.01,
            "Bene_Avg_Age": rng.uniform(68, 76, n), "Bene_Avg_Risk_Scre": rng.uniform(0.8, 2.0, n),
            "year": y,
        })
        df.to_parquet(raw / f"partd_{y}{'_' + state if cfg['data'].get('dev_state') else ''}.parquet", index=False)

    # Fake exclusions: 30% of planted anomalies get excluded later, plus a little random noise
    rows = []
    for i in range(n):
        p = 0.30 if weird[i] else 0.004
        if rng.random() < p:
            date = pd.Timestamp("2022-01-01") + pd.Timedelta(days=int(rng.integers(0, 1500)))
            no_npi = rng.random() < 0.25  # some records have no NPI, testing the name backup match
            rows.append({"LASTNAME": lasts[i], "FIRSTNAME": firsts[i], "MIDNAME": "", "BUSNAME": "",
                         "GENERAL": "", "SPECIALTY": specs[i], "UPIN": "",
                         "NPI": "0000000000" if no_npi else npis[i], "DOB": "", "ADDRESS": "",
                         "CITY": "", "STATE": state, "ZIP": "",
                         "EXCLTYPE": rng.choice(["1128a1", "1128b7", "1128b4"]),
                         "EXCLDATE": date.strftime("%Y%m%d"), "REINDATE": "00000000",
                         "WAIVERDATE": "00000000", "WVRSTATE": ""})
    pd.DataFrame(rows).to_csv(raw / "leie_sample.csv", index=False)
    print(f"Sample data: {n} prescribers, {weird.sum()} planted anomalies, {len(rows)} fake exclusions")
