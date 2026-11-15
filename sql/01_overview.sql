-- A flight is delay-eligible when it operated to its destination and has arrival delay.
SELECT
    substr(flight_date, 1, 4) AS year,
    COUNT(*) AS scheduled_flights,
    COUNT(DISTINCT airline_code) AS airlines,
    COUNT(DISTINCT origin_code) AS origin_codes,
    SUM(cancelled) AS cancelled_flights,
    SUM(diverted) AS diverted_flights,
    SUM(CASE WHEN arrival_delay IS NULL THEN 1 ELSE 0 END) AS missing_arrival_delay,
    SUM(CASE WHEN cancelled = 0 AND diverted = 0 AND arrival_delay IS NULL
        THEN 1 ELSE 0 END) AS missing_delay_on_completed_flights,
    SUM(CASE WHEN cancelled = 0 AND diverted = 0 AND arrival_delay IS NOT NULL
        THEN 1 ELSE 0 END) AS eligible_arrivals,
    SUM(CASE WHEN cancelled = 0 AND diverted = 0 AND arrival_delay >= 15
        THEN 1 ELSE 0 END) AS delayed_arrivals,
    AVG(CASE WHEN cancelled = 0 AND diverted = 0 THEN arrival_delay END) AS mean_arrival_delay,
    MIN(CASE WHEN cancelled = 0 AND diverted = 0 THEN arrival_delay END) AS min_arrival_delay,
    MAX(CASE WHEN cancelled = 0 AND diverted = 0 THEN arrival_delay END) AS max_arrival_delay,
    SUM(CASE WHEN cancelled = 0 AND diverted = 0 AND arrival_delay < 0
        THEN 1 ELSE 0 END) AS early_arrivals
FROM flight
GROUP BY substr(flight_date, 1, 4)
ORDER BY year;
