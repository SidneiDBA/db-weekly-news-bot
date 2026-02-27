def init_db(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS articles_raw (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            title TEXT,
            url TEXT UNIQUE,
            published_at TEXT,
            content TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS articles_scored (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_id INTEGER,
            db_engine TEXT,
            topic TEXT,
            impact_score REAL,
            is_duplicate INTEGER DEFAULT 0
        )
    """)
    conn.commit()