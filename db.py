"""Thin MariaDB helper using PyMySQL. One connection per request."""
import pymysql
from flask import g

import config


def connect(with_database=True):
    params = dict(
        host=config.DB_HOST, port=config.DB_PORT,
        user=config.DB_USER, password=config.DB_PASSWORD,
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor, autocommit=False,
    )
    if with_database:
        params["database"] = config.DB_NAME
    return pymysql.connect(**params)


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def query(sql, args=(), one=False):
    with get_db().cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchone() if one else cur.fetchall()


def execute(sql, args=()):
    """Run INSERT/UPDATE/DELETE. Returns (rows_affected, last_insert_id)."""
    with get_db().cursor() as cur:
        affected = cur.execute(sql, args)
        return affected, cur.lastrowid


def commit():
    get_db().commit()


def rollback():
    get_db().rollback()
