-- Daily units retain October flights and avoid treating flights as independent days.
WITH classified AS (
    SELECT *,
        CASE WHEN cancelled = 0 AND diverted = 0 AND arrival_delay IS NOT NULL
            THEN 1 ELSE 0 END AS eligible,
        CASE
            WHEN scheduled_departure = 2400 THEN 0
            WHEN scheduled_departure BETWEEN 0 AND 2359
                 AND scheduled_departure % 100 < 60 THEN scheduled_departure / 100
        END AS departure_hour
    FROM flight
)
SELECT
    flight_date,
    COUNT(*) AS scheduled_flights,
    SUM(cancelled) AS cancelled_flights,
    SUM(eligible) AS eligible_arrivals,
    SUM(CASE WHEN eligible = 1 AND arrival_delay >= 15 THEN 1 ELSE 0 END) AS delayed_arrivals,
    SUM(CASE WHEN eligible = 1 AND departure_delay IS NOT NULL THEN 1 ELSE 0 END) AS paired_delay_flights,
    AVG(CASE WHEN eligible = 1 AND departure_delay IS NOT NULL THEN departure_delay END) AS mean_departure_delay,
    AVG(CASE WHEN eligible = 1 AND departure_delay IS NOT NULL THEN arrival_delay END) AS mean_arrival_delay,
    SUM(CASE WHEN departure_hour BETWEEN 5 AND 11 THEN 1 ELSE 0 END) AS morning_scheduled,
    SUM(CASE WHEN departure_hour BETWEEN 5 AND 11 THEN cancelled ELSE 0 END) AS morning_cancelled,
    SUM(CASE WHEN departure_hour BETWEEN 5 AND 11 THEN eligible ELSE 0 END) AS morning_eligible,
    SUM(CASE WHEN departure_hour BETWEEN 5 AND 11 AND eligible = 1 AND arrival_delay >= 15
        THEN 1 ELSE 0 END) AS morning_late,
    SUM(CASE WHEN departure_hour BETWEEN 17 AND 23 THEN 1 ELSE 0 END) AS evening_scheduled,
    SUM(CASE WHEN departure_hour BETWEEN 17 AND 23 THEN cancelled ELSE 0 END) AS evening_cancelled,
    SUM(CASE WHEN departure_hour BETWEEN 17 AND 23 THEN eligible ELSE 0 END) AS evening_eligible,
    SUM(CASE WHEN departure_hour BETWEEN 17 AND 23 AND eligible = 1 AND arrival_delay >= 15
        THEN 1 ELSE 0 END) AS evening_late
FROM classified
GROUP BY flight_date
ORDER BY flight_date;
