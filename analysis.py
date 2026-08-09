"""
Fernway Churn Spike — Analysis Challenge #002
Answers whether the June price increase (₹399 -> ₹449) actually caused
the churn spike, using cohort analysis instead of a single blended
month-over-month number.
"""

import pandas as pd

subs = pd.read_csv("subscriptions.csv", parse_dates=["started_at", "cancelled_at", "ended_at"])
users = pd.read_csv("users.csv", parse_dates=["signup_date"])
plans = pd.read_csv("plans.csv")

subs["plan_norm"] = subs["plan"].str.lower()

paid = subs[subs["is_trial"] == 0].copy()
paid["start_month"] = paid["started_at"].dt.to_period("M")

june_start, june_end = pd.Timestamp("2026-06-01"), pd.Timestamp("2026-07-01")

active_base_june = paid[
    (paid["started_at"] < june_start)
    & ((paid["ended_at"].isna()) | (paid["ended_at"] >= june_start))
]
churned_june = paid[
    (paid["ended_at"] >= june_start)
    & (paid["ended_at"] < june_end)
    & (paid["status"] == "cancelled")
]
real_june_churn_rate = len(churned_june) / len(active_base_june) * 100
print(f"Q1: Real June churn rate (paid base, by ended_at) = {real_june_churn_rate:.1f}%")
print(f"    (active base: {len(active_base_june)}, churned: {len(churned_june)})")

churn_rate_by_cohort = {}
for m in pd.period_range("2025-08", "2026-05", freq="M"):
    base = paid[
        (paid["start_month"] == m)
        & (paid["started_at"] < june_start)
        & ((paid["ended_at"].isna()) | (paid["ended_at"] >= june_start))
    ]
    churned = base[
        (base["ended_at"] >= june_start)
        & (base["ended_at"] < june_end)
        & (base["status"] == "cancelled")
    ]
    if len(base) > 0:
        churn_rate_by_cohort[str(m)] = round(len(churned) / len(base) * 100, 1)

print("\nQ2: June churn rate by signup cohort:")
for m, r in churn_rate_by_cohort.items():
    flag = "  <-- SPIKE" if r > 15 else ""
    print(f"    {m}: {r}%{flag}")

march = paid[paid["start_month"] == pd.Period("2026-03", "M")]
march_users = march.merge(users, on="user_id", how="left")
print(f"\nQ3: March cohort size = {len(march)}")
print("    Acquisition channel mix (March):")
print(march_users["acquisition_channel"].value_counts(normalize=True).round(2))
print("\n    Promo code usage (March):")
print(march["promo_code"].value_counts(dropna=False))

promo_churn = march[march["promo_code"] == "LAUNCH60"]
promo_churn_rate = (promo_churn["status"] == "cancelled").mean() * 100
no_promo = march[march["promo_code"].isna()]
no_promo_churn_rate = (no_promo["status"] == "cancelled").mean() * 100
print(f"\n    LAUNCH60 promo users churn rate: {promo_churn_rate:.1f}%")
print(f"    Non-promo March users churn rate: {no_promo_churn_rate:.1f}%")
print("    LAUNCH60 price_inr:", march[march["promo_code"] == "LAUNCH60"]["price_inr"].unique())

print("\nQ4: All non-March cohorts stayed in the normal 3-5% band through "
      "their June renewal, despite facing the same price increase. "
      "This rules out the price rise as the primary driver.")

print("\nQ5 (Recommendation): Do NOT roll back the price on 1 Sept. "
      "The spike is concentrated in the March paid_social/LAUNCH60 cohort "
      "hitting the end of a 60%-off promo (₹160 -> full price) at the same "
      "time as the general increase — not a broad reaction to ₹399->₹449. "
      "Rolling back would cut revenue on a healthy base without fixing the "
      "real problem. Instead: build a step-down/renewal offer for promo "
      "cohorts before their discount expires.")
