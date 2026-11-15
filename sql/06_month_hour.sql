-- Hour is local scheduled departure time, paired with the source service month.
WITH totals AS (
    SELECT
        substr(flight_date, 1, 7) AS month,
        CASE WHEN scheduled_departure = 2400 THEN 0 ELSE scheduled_departure / 100 END
            AS departure_hour,
        COUNT(*) AS scheduled_flights,
        SUM(cancelled) AS cancelled_flights,
        SUM(CASE WHEN cancelled = 0 AND diverted = 0 AND arrival_delay IS NOT NULL
            THEN 1 ELSE 0 END) AS eligible_arrivals,
        SUM(CASE WHEN cancelled = 0 AND diverted = 0 AND arrival_delay >= 15
            THEN 1 ELSE 0 END) AS delayed_arrivals
    FROM flight
    WHERE scheduled_departure = 2400
       OR (scheduled_departure BETWEEN 0 AND 2359 AND scheduled_departure % 100 < 60)
    GROUP BY month, departure_hour
)
SELECT *,
    100.0 * delayed_arrivals / NULLIF(eligible_arrivals, 0) AS late_rate_pct,
    100.0 * cancelled_flights / scheduled_flights AS cancellation_rate_pct
FROM totals
ORDER BY month, departure_hour;
