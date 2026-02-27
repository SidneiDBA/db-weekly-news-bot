import os
import sqlite3
from schema import init_db

def get_conn():
    here = os.path.dirname(__file__)                     # …/src
    db_path = os.path.join(here, "..", "db_news.db")     # ../db_news.db
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path) 
    init_db(conn)
    return conn