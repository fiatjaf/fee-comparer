import psycopg2

from .globals import POSTGRES_URL
from .inspecttransactions import inspecttransactions


def main():
    with psycopg2.connect(POSTGRES_URL) as conn:
        conn.autocommit = True

        with conn.cursor() as db:
            inspecttransactions(db)


main()
