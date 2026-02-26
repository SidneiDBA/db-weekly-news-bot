import sqlite3
from schema import init_db

def get_conn():
    conn = sqlite3.connect("db_news.db")
    init_db(conn)
    return conn