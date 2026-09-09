import sqlite3

from positionpolling import sql


def test_table_exists() -> None:
    try:
        conn = sqlite3.connect(':memory:')
        assert not sql.table_exists(conn, 'data')

        conn.execute('CREATE TABLE data(id INTEGER);')
        assert sql.table_exists(conn, 'data')
    finally:
        conn.close()
