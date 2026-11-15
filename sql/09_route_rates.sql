-- A route is directional. Keep only routes with at least 10,000 eligible arrivals.
WITH totals AS (
    SELECT
        origin_code,
        destination_code,
        COUNT(*) AS eligible_arrivals,
        SUM(CASE WHEN arrival_delay >= 15 THEN 1 ELSE 0 END) AS delayed_arrivals
    FROM flight
    WHERE cancelled = 0 AND diverted = 0 AND arrival_delay IS NOT NULL
    GROUP BY origin_code, destination_code
    HAVING COUNT(*) >= 10000
)
SELECT
    totals.origin_code,
    origin.airport_name AS origin_name,
    totals.destination_code,
    destination.airport_name AS destination_name,
    eligible_arrivals,
    delayed_arrivals,
    100.0 * delayed_arrivals / eligible_arrivals AS late_rate_pct
FROM totals
LEFT JOIN airport AS origin ON totals.origin_code = origin.airport_code
LEFT JOIN airport AS destination ON totals.destination_code = destination.airport_code
ORDER BY late_rate_pct DESC, totals.origin_code, totals.destination_code;
