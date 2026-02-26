from db import get_conn

def dedupe():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE articles_scored
        SET is_duplicate = 1
        WHERE raw_id IN (
            SELECT r1.id
            FROM articles_raw r1
            JOIN articles_raw r2
              ON lower(r1.title) = lower(r2.title)
             AND r1.id > r2.id
        )
    """)

    conn.commit()
    conn.close()