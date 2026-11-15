WITH totals AS (
    SELECT
        substr(flight_date, 1, 7) AS month,
        cancellation_reason_code AS reason_code,
        COUNT(*) AS cancelled_flights
    FROM flight
    WHERE cancelled = 1
    GROUP BY month, cancellation_reason_code
)
SELECT
    month,
    totals.reason_code,
    COALESCE(cancellation_reason.reason_name, 'Unspecified reason') AS reason_name,
    cancelled_flights,
    100.0 * cancelled_flights / SUM(cancelled_flights) OVER (PARTITION BY month)
        AS share_of_cancellations_pct
FROM totals
LEFT JOIN cancellation_reason ON totals.reason_code = cancellation_reason.reason_code
ORDER BY month, cancelled_flights DESC, totals.reason_code;
