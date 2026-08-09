# Fernway Churn Spike — Analysis

## What happened
The dashboard's "17% churn in June" is not accurate. Measured correctly —
paid subscribers only (trial rows excluded, since they've never paid),
and cancellations counted in the month access actually ended (`ended_at`),
not the month the user clicked cancel (`cancelled_at`) — **June's real
churn rate was ~9.1%** (962 of 10,604 active paid subscribers). Elevated
versus the 3–5% baseline, but not the crisis the raw number suggested.

## Was the price increase the cause?
**No — the data rules this out.** If the ₹399 → ₹449 increase (effective
1 June) were driving churn, every cohort renewing in June should show
elevated churn, since all monthly subscribers hit the new price at their
next billing cycle. Instead, churn by signup cohort shows:

| Cohort | June churn rate |
|---|---|
| Aug 2025 – Feb 2026 | 3.3% – 5.1% (normal) |
| **March 2026** | **26.4%** |
| April – May 2026 | 3.8% – 5.2% (normal) |

Only the March cohort spiked. Every other cohort absorbed the same price
increase without any unusual churn.

## What actually happened
The March 2026 cohort (2,409 subscribers, roughly 2x a normal month) was
74% acquired through a `paid_social` campaign, largely on a **LAUNCH60**
promo — 60% off, ₹160/month instead of ₹399. By June, 90 days later, the
promo lapsed:

- LAUNCH60 promo users: **37.4%** churned
- Non-promo March users: 12.1% churned
- All other months' cohorts: 3–5% churned

These users faced a jump from ₹160 to full price (₹449) — a ~180%
increase — not the 12.5% general increase the team is worried about.
This is a **promo-expiry cliff in a low-intent, paid-acquisition cohort**,
not a reaction to the list price change.

## Recommendation
**Do not roll back the price on 1 September.** The general increase is
not what's causing the spike — the rest of the base has absorbed it
fine. Rolling it back would give up margin across the entire healthy
subscriber base without fixing the actual problem.

**Instead:**
1. Build a step-down or targeted retention offer for promo cohorts
   before LAUNCH60 (and similar codes) expire, rather than a hard cliff
   to full price.
2. Review the `paid_social` acquisition channel's cohort quality — a
   channel that converts cheaply but churns at 3–7x baseline once the
   discount ends is not paying for itself the way the headline signup
   numbers suggest.
3. Fix the dashboard's blended churn metric — it currently overstates
   the problem by not separating trial expirations from paid
   cancellations, and by using click-date instead of access-end-date.

## Files
- `analysis.py` — Python analysis, reproduces every number above
- `analysis.sql` — equivalent SQL queries
