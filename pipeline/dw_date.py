from datetime import date

FIRST_DAY = date(1940, 1, 1)


def seed(cursor, until_year):
    cursor.execute(
        """
        INSERT INTO dw.dim_date (date_sk, full_date, year, quarter, month, month_name, day)
        SELECT to_char(d, 'YYYYMMDD')::integer, d::date,
               extract(year FROM d)::smallint, extract(quarter FROM d)::smallint,
               extract(month FROM d)::smallint, to_char(d, 'FMMonth'),
               extract(day FROM d)::smallint
        FROM generate_series(%s::date, make_date(%s, 12, 31), interval '1 day') AS d
        ON CONFLICT (date_sk) DO NOTHING
        """,
        (FIRST_DAY, until_year),
    )
