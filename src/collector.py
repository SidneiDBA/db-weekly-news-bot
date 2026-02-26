import feedparser
from db import get_conn

def collect(feed_url, source_name):
    feed = feedparser.parse(feed_url)
    conn = get_conn()
    cur = conn.cursor()

    for e in feed.entries:
        cur.execute("""
            INSERT OR IGNORE INTO articles_raw
            (source, title, url, published_at, content)
            VALUES (?, ?, ?, ?, ?)
        """, (
            source_name,
            e.title,
            e.link,
            e.get("published"),
            e.get("summary", "")
        ))

    conn.commit()
    conn.close()