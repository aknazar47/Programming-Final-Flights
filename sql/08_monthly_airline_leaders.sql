-- Display one carrier per month among those with at least 5,000 eligible arrivals.
-- Exact ties are resolved by larger eligible count, then by airline code.
WITH totals AS (
    SELECT
        substr(flight_date, 1, 7) AS month,
        airline_code,
        COUNT(*) AS eligible_arrivals,
        SUM(CASE WHEN arrival_delay >= 15 THEN 1 ELSE 0 END) AS delayed_arrivals
    FROM flight
    WHERE cancelled = 0 AND diverted = 0 AND arrival_delay IS NOT NULL
    GROUP BY month, airline_code
    HAVING COUNT(*) >= 5000
),
rates AS (
    SELECT *,
        100.0 * delayed_arrivals / eligible_arrivals AS late_rate_pct
    FROM totals
),
numbered AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY month ORDER BY late_rate_pct DESC, eligible_arrivals DESC, airline_code
        ) AS month_row
    FROM rates
)
SELECT
    numbered.month,
    numbered.airline_code,
    airline.airline_name,
    numbered.eligible_arrivals,
    numbered.delayed_arrivals,
    numbered.late_rate_pct,
    numbered.month_row
FROM numbered
JOIN airline ON numbered.airline_code = airline.airline_code
WHERE month_row = 1
ORDER BY month;
