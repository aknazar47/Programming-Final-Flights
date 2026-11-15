-- Add the flight counts across the latest three months before dividing.
-- January and February have partial windows in the 2015 dataset.
WITH totals AS (
    SELECT
        substr(flight_date, 1, 7) AS month,
        COUNT(*) AS scheduled_flights,
        SUM(cancelled) AS cancelled_flights,
        SUM(CASE WHEN cancelled = 0 AND diverted = 0 AND arrival_delay IS NOT NULL
            THEN 1 ELSE 0 END) AS eligible_arrivals,
        SUM(CASE WHEN cancelled = 0 AND diverted = 0 AND arrival_delay >= 15
            THEN 1 ELSE 0 END) AS delayed_arrivals
    FROM flight
    GROUP BY substr(flight_date, 1, 7)
)
SELECT *,
    100.0 * delayed_arrivals / NULLIF(eligible_arrivals, 0) AS late_rate_pct,
    100.0 * cancelled_flights / scheduled_flights AS cancellation_rate_pct,
    COUNT(*) OVER trailing AS months_in_window,
    100.0 * SUM(delayed_arrivals) OVER trailing
        / NULLIF(SUM(eligible_arrivals) OVER trailing, 0) AS rolling_late_rate_pct,
    100.0 * SUM(cancelled_flights) OVER trailing
        / SUM(scheduled_flights) OVER trailing AS rolling_cancellation_rate_pct
FROM totals
WINDOW trailing AS (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
ORDER BY month;
