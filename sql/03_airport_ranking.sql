-- Use origins with at least 10,000 delay-eligible arrivals across the year.
WITH totals AS (
    SELECT
        origin_code AS airport_code,
        COUNT(*) AS scheduled_flights,
        SUM(cancelled) AS cancelled_flights,
        SUM(CASE WHEN cancelled = 0 AND diverted = 0 AND arrival_delay IS NOT NULL
            THEN 1 ELSE 0 END) AS eligible_arrivals,
        SUM(CASE WHEN cancelled = 0 AND diverted = 0 AND arrival_delay >= 15
            THEN 1 ELSE 0 END) AS delayed_arrivals
    FROM flight
    GROUP BY origin_code
    HAVING eligible_arrivals >= 10000
),
rates AS (
    SELECT *,
        100.0 * delayed_arrivals / eligible_arrivals AS late_rate_pct,
        100.0 * cancelled_flights / scheduled_flights AS cancellation_rate_pct
    FROM totals
)
SELECT
    rates.airport_code,
    airport.airport_name,
    airport.city,
    airport.state,
    rates.scheduled_flights,
    rates.cancelled_flights,
    rates.eligible_arrivals,
    rates.delayed_arrivals,
    rates.late_rate_pct,
    rates.cancellation_rate_pct,
    RANK() OVER (ORDER BY late_rate_pct DESC) AS delay_rank
FROM rates
LEFT JOIN airport ON rates.airport_code = airport.airport_code
ORDER BY delay_rank, rates.airport_code;
