# Fernway Churn Spike Analysis

## Project overview
SQL and Python analysis of why Fernway's reported June 2026 churn jumped, and
whether the list-price increase (₹399 to ₹449, effective 1 June) was the cause.

## Business problem
The dashboard reported a 17% churn rate for June. Leadership was considering
reversing the price increase on 1 September. The questions here:

1. What was June churn once measured consistently?
2. Which subscriber groups account for it?
3. Does the data support blaming the price increase?

## Dataset
Three CSV files, expected in a `data/` folder (not included in this repository):

| File | Columns used |
|---|---|
| `subscriptions.csv` | `user_id`, `is_trial`, `started_at`, `ended_at`, `status`, `promo_code`, `price_inr` |
| `users.csv` | `user_id`, `acquisition_channel` |

`plans.csv` was loaded by the earlier version of the script but never used, so
it is no longer read.

## Metric definitions
Python and SQL use the same rules.

- **Unit:** one paid subscription row (`is_trial = 0`). Trials are excluded.
- **Opening base for a month:** paid subscriptions that started before the first
  day of the month and had not ended before it (`ended_at` empty or on/after that day).
- **Churned:** a subscription in the opening base whose `ended_at` falls in the
  month and whose `status` is `cancelled`.
- **Churn rate:** churned / opening base. Churned is always a subset of the base.
- **Cohort:** month of `started_at` on the paid subscription.
- **Promo groups:** `LAUNCH60`, `Other promo` (any other non-empty code), `No promo`.
  Codes are trimmed and upper-cased first. The groups do not overlap and cover every row.

## Data preparation and quality checks
Both scripts report these before any result:

- exact duplicate rows (removed), and duplicate `user_id` values in `users`
- `is_trial` values (only `0` is treated as paid, so unexpected values show up)
- dates that are present but unparseable, and rows ending before they start
- statuses of subscriptions that ended in June (only `cancelled` counts as churn)

## SQL analysis
`analysis.sql` (SQLite). Two temporary views, `paid_subs` and `june_base`, hold the
cleaning and eligibility rules, so every query uses the same population. Queries:
overall June churn, monthly churn trend, June churn by cohort, March channel mix,
and March churn by promo group.

## Python analysis
`analysis.py` (pandas). It has the same sections as the SQL file. Each result table
comes from one function, and the script asserts that cohort rows add up to the
overall figure and that the promo groups cover the March cohort exactly once.

## Key findings
**Not yet verified.** The CSV files were not in the repository when the code was
corrected, so the corrected scripts have not been run on the real data. The earlier
README figures below were produced with the old logic and should not be quoted:

- 9.1% overall June churn (962 / 10,604). The numerator also counted subscriptions
  that started in June, which were not in the 1 June base.
- 26.4% March cohort June churn.
- 37.4% (LAUNCH60) vs 12.1% (non-promo). These used `status = 'cancelled'` at
  extraction, which is not a June figure, and put other promo codes in neither or the wrong group.

After running the scripts, replace this section with the printed values.

## Interpretation guide
What the output can and cannot show once it is run:

- **Observed:** whether one cohort's June churn stands out, and whether churn
  excluding LAUNCH60 subscriptions changed from earlier months.
- **Possible explanation:** the March cohort was acquired with a 60% discount that
  lapsed around June, at the same time as the list-price change. Both events hit
  that group together, so their effects cannot be separated.
- **Not supported:** claiming the price increase had no effect. Even if other
  cohorts look stable, this is an observational comparison with no control group.

## Recommendations
Cautious, pending the verified numbers:

1. Do not reverse the list price on the strength of this analysis alone. If the
   non-promo base shows no change, there is no sign of a broad effect, but monitor
   July and August churn before treating that as settled.
2. Test a step-down or renewal offer for promo cohorts before the discount ends.
3. Review retention by acquisition channel for the March cohort.
4. Report churn with one documented definition on the dashboard.

## Limitations
- Extraction date and promo duration are not in the data, so promo expiry timing is inferred.
- `price_inr` is stored per subscription, so it does not show what an existing
  subscriber was charged after 1 June.
- Plan type (monthly vs annual) is not separated, and annual subscribers do not renew in June.
- Churn is counted per subscription, not per user.
- Cohort start month assumes `started_at` is the paid start date.
- Churn is limited to `cancelled`. Other end statuses are listed but not counted.

## Repository structure
```
analysis.py     Python analysis
analysis.sql    SQLite queries
README.md
data/           CSV files (add locally)
```

## Reproduce
Requires Python 3.9+, pandas 2.0+ and any recent SQLite 3.

```bash
pip install "pandas>=2.0"
python analysis.py
```

SQL, with the CSVs in `data/`:
```bash
sqlite3 fernway.db
.mode csv
.import data/subscriptions.csv subscriptions
.import data/users.csv users
.mode column
.headers on
.read analysis.sql
```
Empty CSV cells import as empty strings, not NULL. The SQL handles that.

## Tools
Python, pandas, SQLite.
