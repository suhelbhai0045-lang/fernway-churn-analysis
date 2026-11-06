-- Fernway churn analysis (SQLite)
-- Same definitions as analysis.py:
--   unit of analysis : one paid subscription (is_trial = 0)
--   opening base     : started before the window start and not yet ended on it
--   churned          : in the opening base, ended inside the window, status = 'cancelled'
--   churn rate       : churned / opening base
-- Tables subscriptions and users are loaded from the CSVs as text. Empty cells
-- arrive as '' (not NULL), so every nullable column is cleaned with NULLIF(TRIM(...), '').

DROP VIEW IF EXISTS temp.paid_subs;
DROP VIEW IF EXISTS temp.june_base;
DROP VIEW IF EXISTS temp.clean_users;

-- Paid subscriptions with typed, normalised columns. DISTINCT removes exact duplicate rows.
CREATE TEMP VIEW paid_subs AS
SELECT
    user_id,
    date(NULLIF(TRIM(started_at), ''))                  AS started_on,
    strftime('%Y-%m', NULLIF(TRIM(started_at), ''))     AS start_month,
    date(NULLIF(TRIM(ended_at), ''))                    AS ended_on,
    LOWER(TRIM(status))                                 AS status,
    CASE
        WHEN UPPER(TRIM(promo_code)) = 'LAUNCH60'       THEN 'LAUNCH60'
        WHEN NULLIF(TRIM(promo_code), '') IS NOT NULL   THEN 'Other promo'
        ELSE 'No promo'
    END                                                 AS promo_group,
    CAST(NULLIF(TRIM(price_inr), '') AS REAL)           AS price_inr
FROM (SELECT DISTINCT * FROM subscriptions)
WHERE TRIM(is_trial) = '0';

-- Paid subscriptions active on 1 June, flagged if they churned in June.
CREATE TEMP VIEW june_base AS
SELECT
    *,
    CASE WHEN ended_on >= '2026-06-01' AND ended_on < '2026-07-01' AND status = 'cancelled'
         THEN 1 ELSE 0 END AS churned
FROM paid_subs
WHERE started_on < '2026-06-01'
  AND (ended_on IS NULL OR ended_on >= '2026-06-01');

-- One row per user. If a user appears with several different channels, the
-- alphabetically first one is kept, so the join in Q4 can never double count.
CREATE TEMP VIEW clean_users AS
SELECT
    user_id,
    MIN(COALESCE(NULLIF(TRIM(acquisition_channel), ''), '(missing)')) AS acquisition_channel
FROM users
GROUP BY user_id;

-- Q0a: data quality - row counts, exact duplicates, users listed with conflicting channels
SELECT
    (SELECT COUNT(*) FROM subscriptions)                                  AS subscription_rows,
    (SELECT COUNT(*) FROM (SELECT DISTINCT * FROM subscriptions))         AS distinct_rows,
    (SELECT COUNT(*) FROM (SELECT DISTINCT user_id,
            COALESCE(NULLIF(TRIM(acquisition_channel), ''), '(missing)') FROM users))
      - (SELECT COUNT(DISTINCT user_id) FROM users)                       AS extra_user_channel_rows;

-- Q0b: data quality - is_trial values (only '0' is treated as paid)
SELECT TRIM(is_trial) AS is_trial, COUNT(*) AS n
FROM (SELECT DISTINCT * FROM subscriptions)
GROUP BY TRIM(is_trial)
ORDER BY is_trial;

-- Q0c: data quality - dates that are present but cannot be parsed, and end before start
SELECT
    SUM(CASE WHEN NULLIF(TRIM(started_at), '') IS NOT NULL AND date(NULLIF(TRIM(started_at), '')) IS NULL THEN 1 ELSE 0 END) AS unparseable_started_at,
    SUM(CASE WHEN NULLIF(TRIM(ended_at), '')   IS NOT NULL AND date(NULLIF(TRIM(ended_at), ''))   IS NULL THEN 1 ELSE 0 END) AS unparseable_ended_at,
    SUM(CASE WHEN date(NULLIF(TRIM(ended_at), '')) < date(NULLIF(TRIM(started_at), '')) THEN 1 ELSE 0 END) AS ended_before_started
FROM (SELECT DISTINCT * FROM subscriptions);

-- Q1: June churn, paid subscriptions active on 1 June
SELECT
    COUNT(*)                                          AS opening_base,
    SUM(churned)                                      AS churned,
    ROUND(100.0 * SUM(churned) / NULLIF(COUNT(*), 0), 1) AS churn_pct
FROM june_base;

-- Q1b: June endings inside the opening base, by status (only 'cancelled' counts as churn)
SELECT status, COUNT(*) AS n
FROM june_base
WHERE ended_on >= '2026-06-01' AND ended_on < '2026-07-01'
GROUP BY status
ORDER BY status;

-- Q2: Monthly churn with the same definition, second set of columns excludes LAUNCH60
WITH months(month_start, next_month_start) AS (
    VALUES ('2026-01-01', '2026-02-01'), ('2026-02-01', '2026-03-01'),
           ('2026-03-01', '2026-04-01'), ('2026-04-01', '2026-05-01'),
           ('2026-05-01', '2026-06-01'), ('2026-06-01', '2026-07-01')
),
monthly_base AS (
    SELECT
        m.month_start,
        p.promo_group,
        CASE WHEN p.ended_on >= m.month_start AND p.ended_on < m.next_month_start AND p.status = 'cancelled'
             THEN 1 ELSE 0 END AS churned
    FROM months AS m
    JOIN paid_subs AS p
      ON p.started_on < m.month_start
     AND (p.ended_on IS NULL OR p.ended_on >= m.month_start)
)
SELECT
    month_start,
    COUNT(*)                                                                     AS opening_base,
    SUM(churned)                                                                 AS churned,
    ROUND(100.0 * SUM(churned) / NULLIF(COUNT(*), 0), 1)                         AS churn_pct,
    SUM(CASE WHEN promo_group <> 'LAUNCH60' THEN 1 ELSE 0 END)                   AS base_excl_launch60,
    SUM(CASE WHEN promo_group <> 'LAUNCH60' THEN churned ELSE 0 END)             AS churned_excl_launch60,
    ROUND(100.0 * SUM(CASE WHEN promo_group <> 'LAUNCH60' THEN churned ELSE 0 END)
          / NULLIF(SUM(CASE WHEN promo_group <> 'LAUNCH60' THEN 1 ELSE 0 END), 0), 1) AS churn_pct_excl_launch60
FROM monthly_base
GROUP BY month_start
ORDER BY month_start;

-- Q3: June churn by start-month cohort (opening base only, so the cohort rows sum to Q1)
SELECT
    start_month,
    COUNT(*)                                          AS opening_base,
    SUM(churned)                                      AS churned,
    ROUND(100.0 * SUM(churned) / NULLIF(COUNT(*), 0), 1) AS churn_pct
FROM june_base
GROUP BY start_month
ORDER BY start_month;

-- Q4: Acquisition channel mix of the March 2026 cohort (all paid subscriptions started that month)
WITH march AS (
    SELECT COALESCE(u.acquisition_channel, '(missing)') AS acquisition_channel
    FROM paid_subs AS p
    LEFT JOIN clean_users AS u ON u.user_id = p.user_id
    WHERE p.start_month = '2026-03'
)
SELECT
    acquisition_channel,
    COUNT(*)                                                       AS n,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM march), 1)      AS pct
FROM march
GROUP BY acquisition_channel
ORDER BY n DESC, acquisition_channel;

-- Q5: Promo groups within the March 2026 cohort
--   june_churn_pct       = churn among those active on 1 June (comparable to Q3)
--   cancelled_to_date_pct = status 'cancelled' at extraction, any month (not a June metric)
WITH groups(promo_group) AS (VALUES ('LAUNCH60'), ('Other promo'), ('No promo')),
cohort AS (
    SELECT
        p.promo_group,
        p.status,
        p.price_inr,
        CASE WHEN p.started_on < '2026-06-01' AND (p.ended_on IS NULL OR p.ended_on >= '2026-06-01')
             THEN 1 ELSE 0 END AS in_june_base,
        CASE WHEN p.started_on < '2026-06-01' AND (p.ended_on IS NULL OR p.ended_on >= '2026-06-01')
                  AND p.ended_on >= '2026-06-01' AND p.ended_on < '2026-07-01' AND p.status = 'cancelled'
             THEN 1 ELSE 0 END AS churned_june
    FROM paid_subs AS p
    WHERE p.start_month = '2026-03'
)
SELECT
    g.promo_group,
    COUNT(c.promo_group)                                                    AS paid_subs,
    COALESCE(SUM(CASE WHEN c.status = 'cancelled' THEN 1 ELSE 0 END), 0)   AS cancelled_to_date,
    ROUND(100.0 * SUM(CASE WHEN c.status = 'cancelled' THEN 1 ELSE 0 END)
          / NULLIF(COUNT(c.promo_group), 0), 1)                             AS cancelled_to_date_pct,
    COALESCE(SUM(c.in_june_base), 0)                                        AS june_opening_base,
    COALESCE(SUM(c.churned_june), 0)                                        AS june_churned,
    ROUND(100.0 * SUM(c.churned_june) / NULLIF(SUM(c.in_june_base), 0), 1)  AS june_churn_pct,
    MIN(c.price_inr)                                                        AS min_price_inr,
    MAX(c.price_inr)                                                        AS max_price_inr
FROM groups AS g
LEFT JOIN cohort AS c ON c.promo_group = g.promo_group
GROUP BY g.promo_group
ORDER BY CASE g.promo_group WHEN 'LAUNCH60' THEN 1 WHEN 'Other promo' THEN 2 ELSE 3 END;
