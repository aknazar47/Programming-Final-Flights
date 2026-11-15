-- Aggregate routes before joining their dimensions to avoid a join per flight.
WITH routes AS (
    SELECT
        substr(flight_date, 1, 7) AS month,
        origin_code,
        destination_code,
        COUNT(*) AS scheduled_flights
    FROM flight
    GROUP BY month, origin_code, destination_code
)
SELECT
    month,
    SUM(scheduled_flights) AS scheduled_flights,
    SUM(CASE WHEN origin.airport_name IS NULL THEN scheduled_flights ELSE 0 END)
        AS origin_missing_metadata_flights,
    SUM(CASE WHEN destination.airport_name IS NULL THEN scheduled_flights ELSE 0 END)
        AS destination_missing_metadata_flights,
    SUM(CASE WHEN origin.airport_name IS NULL OR destination.airport_name IS NULL
        THEN scheduled_flights ELSE 0 END) AS either_missing_metadata_flights,
    COUNT(DISTINCT CASE WHEN origin.airport_name IS NULL THEN routes.origin_code END)
        AS distinct_unmatched_origins
FROM routes
LEFT JOIN airport AS origin ON routes.origin_code = origin.airport_code
LEFT JOIN airport AS destination ON routes.destination_code = destination.airport_code
GROUP BY month
ORDER BY month;
