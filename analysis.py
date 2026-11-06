"""
Fernway churn analysis (Python).

Business question: was the June 2026 churn spike caused by the list-price
increase (Rs 399 -> Rs 449), or by something else?

Metric definitions (analysis.sql uses exactly the same rules)
-------------------------------------------------------------
Unit of analysis : one paid subscription row (is_trial = 0).
Opening base     : paid subscriptions that started before the window start and
                   had not already ended (ended_at is empty or >= window start).
Churned          : a subscription in the opening base whose ended_at falls inside
                   the window and whose status is 'cancelled'.
Churn rate       : churned / opening base. Because churned is a subset of the
                   opening base, numerator and denominator are the same population.
Cohort           : calendar month of the paid subscription's started_at.
Promo groups     : LAUNCH60, Other promo (any other non-empty code), No promo.
                   Mutually exclusive and together they cover every paid row.
"""

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"

JUNE_START = pd.Timestamp("2026-06-01")
JULY_START = pd.Timestamp("2026-07-01")
FOCUS_COHORT = "2026-03"            # the cohort that spiked in the original analysis
FOCUS_PROMO = "LAUNCH60"
PROMO_GROUPS = [FOCUS_PROMO, "Other promo", "No promo"]
TREND_MONTHS = pd.date_range("2026-01-01", "2026-06-01", freq="MS")  # churn trend window


def pct(numerator, denominator):
    """Percentage rounded to 1 decimal; NaN instead of a division-by-zero error."""
    return round(100 * numerator / denominator, 1) if denominator else float("nan")


# --------------------------------------------------------------------------
# Loading and cleaning
# --------------------------------------------------------------------------
def load_raw():
    # Read everything as text and treat only empty cells as missing, so the
    # data is interpreted the same way SQLite's CSV import interprets it.
    read = lambda name: pd.read_csv(DATA_DIR / name, dtype=str, keep_default_na=False, na_values=[""])
    return read("subscriptions.csv"), read("users.csv")


def prepare_subscriptions(subs_raw):
    subs = subs_raw.drop_duplicates().copy()          # exact duplicate rows only
    subs["started_at"] = pd.to_datetime(subs["started_at"], format="ISO8601", errors="coerce")
    subs["ended_at"] = pd.to_datetime(subs["ended_at"], format="ISO8601", errors="coerce")
    subs["status"] = subs["status"].str.strip().str.lower()
    subs["price_inr"] = pd.to_numeric(subs["price_inr"], errors="coerce")

    promo = subs["promo_code"].str.strip().str.upper()
    promo = promo.mask(promo == "")                    # blank code = no promo
    subs["promo_group"] = "No promo"
    subs.loc[promo.notna(), "promo_group"] = "Other promo"
    subs.loc[promo == FOCUS_PROMO, "promo_group"] = FOCUS_PROMO

    subs["start_month"] = subs["started_at"].dt.strftime("%Y-%m")
    return subs


def paid_only(subs):
    return subs[subs["is_trial"].str.strip() == "0"].copy()


def user_channel_pairs(users_raw):
    """Distinct (user_id, cleaned channel) pairs; a user with 2 channels appears twice."""
    pairs = users_raw[["user_id", "acquisition_channel"]].copy()
    pairs["acquisition_channel"] = pairs["acquisition_channel"].str.strip().mask(lambda s: s == "").fillna("(missing)")
    return pairs.drop_duplicates()


def prepare_users(users_raw):
    """One row per user. If a user has several channels, keep the alphabetically first
    (same rule as MIN() in analysis.sql), so the Q4 merge cannot double count."""
    pairs = user_channel_pairs(users_raw)
    return pairs.sort_values(["user_id", "acquisition_channel"]).drop_duplicates("user_id").reset_index(drop=True)


def data_quality_report(subs_raw, subs, users_raw):
    print("Q0: Data quality checks")
    print(f"    subscriptions rows: {len(subs_raw)}, exact duplicate rows removed: {len(subs_raw) - len(subs)}")
    print("    is_trial values (only '0' is treated as paid):")
    print(subs["is_trial"].value_counts(dropna=False).to_string())
    bad_start = int((subs_raw.drop_duplicates()["started_at"].notna() & subs["started_at"].isna()).sum())
    bad_end = int((subs_raw.drop_duplicates()["ended_at"].notna() & subs["ended_at"].isna()).sum())
    print(f"    unparseable started_at: {bad_start}, unparseable ended_at: {bad_end}")
    print(f"    rows with ended_at before started_at: {int((subs['ended_at'] < subs['started_at']).sum())}")
    pairs = user_channel_pairs(users_raw)
    print(f"    extra user rows with conflicting channels in users: {int(pairs['user_id'].duplicated().sum())}")


# --------------------------------------------------------------------------
# Core metric
# --------------------------------------------------------------------------
def opening_base(paid, window_start, window_end):
    """Paid subscriptions active at window_start, flagged if they churned in the window."""
    in_base = paid["started_at"].lt(window_start) & (
        paid["ended_at"].isna() | paid["ended_at"].ge(window_start)
    )
    base = paid[in_base].copy()
    base["churned"] = (
        base["ended_at"].ge(window_start)
        & base["ended_at"].lt(window_end)
        & base["status"].eq("cancelled")
    )
    return base


# --------------------------------------------------------------------------
# Result tables (each mirrors one query in analysis.sql)
# --------------------------------------------------------------------------
def overall_june(base):
    n, c = len(base), int(base["churned"].sum())
    return pd.DataFrame([{"opening_base": n, "churned": c, "churn_pct": pct(c, n)}])


def june_endings_by_status(base):
    ended = base[base["ended_at"].ge(JUNE_START) & base["ended_at"].lt(JULY_START)]
    return (ended.groupby("status").size().rename("n").reset_index().sort_values("status").reset_index(drop=True))


def monthly_trend(paid):
    rows = []
    for start in TREND_MONTHS:
        base = opening_base(paid, start, start + pd.offsets.MonthBegin(1))
        if base.empty:
            continue
        rest = base[base["promo_group"] != FOCUS_PROMO]
        rows.append({
            "month_start": start.strftime("%Y-%m-%d"),
            "opening_base": len(base), "churned": int(base["churned"].sum()),
            "churn_pct": pct(base["churned"].sum(), len(base)),
            "base_excl_launch60": len(rest), "churned_excl_launch60": int(rest["churned"].sum()),
            "churn_pct_excl_launch60": pct(rest["churned"].sum(), len(rest)),
        })
    return pd.DataFrame(rows)


def cohort_churn(base):
    g = base.groupby("start_month")["churned"].agg(opening_base="size", churned="sum").reset_index()
    g["churned"] = g["churned"].astype(int)
    g["churn_pct"] = [pct(c, n) for c, n in zip(g["churned"], g["opening_base"])]
    return g.sort_values("start_month").reset_index(drop=True)


def channel_mix(paid, users):
    cohort = paid[paid["start_month"] == FOCUS_COHORT].merge(
        users, on="user_id", how="left", validate="many_to_one")
    cohort["acquisition_channel"] = cohort["acquisition_channel"].fillna("(missing)")
    g = cohort.groupby("acquisition_channel").size().rename("n").reset_index()
    g["pct"] = [pct(n, len(cohort)) for n in g["n"]]
    return g.sort_values(["n", "acquisition_channel"], ascending=[False, True]).reset_index(drop=True)


def promo_churn(paid, base):
    cohort_all = paid[paid["start_month"] == FOCUS_COHORT]
    cohort_base = base[base["start_month"] == FOCUS_COHORT]
    rows = []
    for group in PROMO_GROUPS:
        a = cohort_all[cohort_all["promo_group"] == group]
        b = cohort_base[cohort_base["promo_group"] == group]
        cancelled_to_date = int((a["status"] == "cancelled").sum())
        rows.append({
            "promo_group": group,
            "paid_subs": len(a),
            "cancelled_to_date": cancelled_to_date,
            "cancelled_to_date_pct": pct(cancelled_to_date, len(a)),
            "june_opening_base": len(b),
            "june_churned": int(b["churned"].sum()),
            "june_churn_pct": pct(b["churned"].sum(), len(b)),
            "min_price_inr": a["price_inr"].min(),
            "max_price_inr": a["price_inr"].max(),
        })
    result = pd.DataFrame(rows)
    assert result["paid_subs"].sum() == len(cohort_all), "promo groups must cover the cohort exactly once"
    return result


def main():
    subs_raw, users_raw = load_raw()
    subs = prepare_subscriptions(subs_raw)
    users = prepare_users(users_raw)
    paid = paid_only(subs)
    base = opening_base(paid, JUNE_START, JULY_START)

    data_quality_report(subs_raw, subs, users_raw)

    overall = overall_june(base)
    print("\nQ1: June churn, paid subscriptions active on 1 June")
    print(overall.to_string(index=False))
    print("\n    June endings inside the opening base, by status (only 'cancelled' counts as churn)")
    print(june_endings_by_status(base).to_string(index=False))

    print("\nQ2: Monthly churn, same definition; second set of columns excludes LAUNCH60 subscriptions")
    print(monthly_trend(paid).to_string(index=False))

    cohorts = cohort_churn(base)
    assert cohorts["opening_base"].sum() == len(base) and cohorts["churned"].sum() == base["churned"].sum()
    print("\nQ3: June churn by start-month cohort (opening base only)")
    print(cohorts.to_string(index=False))

    print(f"\nQ4: Acquisition channel mix, {FOCUS_COHORT} cohort (all paid subscriptions started that month)")
    print(channel_mix(paid, users).to_string(index=False))

    print(f"\nQ5: Promo groups within the {FOCUS_COHORT} cohort")
    print("    june_churn_pct = churn among those active on 1 June (comparable to Q3).")
    print("    cancelled_to_date_pct = status 'cancelled' at extraction, any month (not a June metric).")
    print(promo_churn(paid, base).to_string(index=False))


if __name__ == "__main__":
    main()
