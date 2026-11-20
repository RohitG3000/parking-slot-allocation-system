"""Create the database, tables and starter data.  Run once:  python init_db.py"""
from werkzeug.security import generate_password_hash

import db
from utils import next_slot_numbers


def run_schema(conn):
    with open("schema.sql", encoding="utf-8") as f:
        statements = [s.strip() for s in f.read().split(";") if s.strip()]
    with conn.cursor() as cur:
        for stmt in statements:
            cur.execute(stmt)
    conn.commit()


def seed(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM users")
        if cur.fetchone()["n"] == 0:
            cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s)",
                        ("admin", generate_password_hash("admin123"), "admin"))
            cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s)",
                        ("operator", generate_password_hash("operator123"), "operator"))
        cur.execute("SELECT COUNT(*) AS n FROM rates")
        if cur.fetchone()["n"] == 0:
            cur.execute("INSERT INTO rates VALUES ('2W', 10.00, 5.00)")
            cur.execute("INSERT INTO rates VALUES ('4W', 20.00, 10.00)")
        cur.execute("SELECT COUNT(*) AS n FROM slots")
        if cur.fetchone()["n"] == 0:
            for level, slot_type, count in (("G", "2W", 6), ("G", "4W", 6), ("1", "4W", 6)):
                for slot_no in next_slot_numbers([], level, slot_type, count):
                    cur.execute("INSERT INTO slots (slot_no, slot_type, level) VALUES (%s,%s,%s)",
                                (slot_no, slot_type, level))
    conn.commit()


if __name__ == "__main__":
    conn = db.connect(with_database=False)
    run_schema(conn)
    conn.close()
    conn = db.connect()
    seed(conn)
    conn.close()
    print("Database ready.")
    print("Login: admin / admin123   or   operator / operator123  (change these passwords!)")
