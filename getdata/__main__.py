import psycopg2

from .globals import POSTGRES_URL
from .run_day import run_day


def main():
    with psycopg2.connect(POSTGRES_URL) as conn:
        conn.autocommit = True

        with conn.cursor() as db:
            run_day(db)


main()
