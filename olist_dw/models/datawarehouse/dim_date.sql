SELECT
    strftime(d, '%Y-%m-%d') AS id,
    d AS full_date,
    date_part('year', d) AS year,
    date_part('quarter', d) AS quarter,
    strftime(d, '%Y') || '-Q' || CAST(date_part('quarter', d) AS VARCHAR) AS year_quarter,
    date_part('month', d) AS month,
    monthname(d) AS month_name,
    date_part('day', d) AS day,
    date_part('dow', d) AS week_day,
    dayname(d) AS day_name,
    CASE
        WHEN date_part('dow', d) IN (0, 6) THEN 0
        ELSE 1
    END AS day_is_weekday
FROM (
    SELECT d
    FROM generate_series(DATE '2016-01-01', DATE '2020-12-31', INTERVAL 1 DAY) AS t(d)
)
