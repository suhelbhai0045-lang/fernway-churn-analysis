-- Fernway Churn Spike — SQL analysis
-- Assumes subscriptions, users, plans loaded as tables (SQLite/Postgres syntax)

-- Q1: Real June churn rate (paid subscribers only, by ended_at, not cancelled_at)
WITH paid AS (
    SELECT *
    FROM subscriptions
    WHERE is_trial = 0
),
active_base_june AS (
    SELECT * FROM paid
    WHERE started_at < '2026-06-01'
      AND (ended_at IS NULL OR ended_at >= '2026-06-01')
),
churned_june AS (
    SELECT * FROM paid
    WHERE ended_at >= '2026-06-01' AND ended_at < '2026-07-01'
      AND status = 'cancelled'
)
SELECT
    (SELECT COUNT(*) FROM active_base_june)  AS active_base,
    (SELECT COUNT(*) FROM churned_june)      AS churned,
    ROUND(100.0 * (SELECT COUNT(*) FROM churned_june)
                 / (SELECT COUNT(*) FROM active_base_june), 1) AS real_june_churn_pct;

-- Q2: June churn rate by signup cohort (isolates which cohort is spiking)
WITH paid AS (
    SELECT *, strftime('%Y-%m', started_at) AS start_month
    FROM subscriptions WHERE is_trial = 0
),
base AS (
    SELECT start_month, COUNT(*) AS base_n
    FROM paid
    WHERE started_at < '2026-06-01'
      AND (ended_at IS NULL OR ended_at >= '2026-06-01')
    GROUP BY start_month
),
churn AS (
    SELECT start_month, COUNT(*) AS churn_n
    FROM paid
    WHERE ended_at >= '2026-06-01' AND ended_at < '2026-07-01'
      AND status = 'cancelled'
    GROUP BY start_month
)
SELECT b.start_month, b.base_n, COALESCE(c.churn_n,0) AS churn_n,
       ROUND(100.0 * COALESCE(c.churn_n,0) / b.base_n, 1) AS churn_pct
FROM base b LEFT JOIN churn c ON b.start_month = c.start_month
ORDER BY b.start_month;

-- Q3: What makes the March cohort different? Acquisition channel + promo mix
SELECT u.acquisition_channel, COUNT(*) AS n,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM subscriptions s
JOIN users u ON s.user_id = u.user_id
WHERE s.is_trial = 0
  AND strftime('%Y-%m', s.started_at) = '2026-03'
GROUP BY u.acquisition_channel
ORDER BY n DESC;

-- Promo cohort churn rate vs non-promo, within March signups
SELECT
    CASE WHEN promo_code = 'LAUNCH60' THEN 'promo' ELSE 'no_promo' END AS grp,
    COUNT(*) AS n,
    ROUND(100.0 * SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) / COUNT(*), 1) AS churn_pct
FROM subscriptions
WHERE is_trial = 0 AND strftime('%Y-%m', started_at) = '2026-03'
GROUP BY grp;
