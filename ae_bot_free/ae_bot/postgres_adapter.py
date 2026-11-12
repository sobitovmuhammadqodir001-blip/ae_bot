"""Mavjud Database interfeysi uchun PostgreSQL adapteri."""
import psycopg
from psycopg.rows import dict_row

class Connection:
    def __init__(self, url):
        self.url = url

    def execute(self, sql, params=()):
        sql = sql.replace("?", "%s")
        with psycopg.connect(self.url, autocommit=True, row_factory=dict_row, connect_timeout=20) as conn:
            if sql.lstrip().startswith("INSERT INTO topics"):
                cur = conn.execute(sql + " RETURNING id", params)
                return InsertResult(cur.fetchone()["id"])
            cur = conn.execute(sql, params)
            return Rows(cur.fetchall() if cur.description else [])

    def executescript(self, sql):
        sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
        sql = sql.replace("user_id INTEGER", "user_id BIGINT").replace("topic_id INTEGER", "topic_id BIGINT").replace("current_topic INTEGER", "current_topic BIGINT")
        with psycopg.connect(self.url, row_factory=dict_row, connect_timeout=20) as conn:
            for statement in sql.split(";"):
                if statement.strip():
                    conn.execute(statement)

    def commit(self):
        pass

    def close(self):
        pass

class InsertResult:
    def __init__(self, value):
        self.lastrowid = value

class Rows:
    def __init__(self, rows):
        self.rows = rows
    def fetchone(self):
        return self.rows[0] if self.rows else None
    def fetchall(self):
        return self.rows
