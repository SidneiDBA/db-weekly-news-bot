from db import get_conn
from llm import call_llm
from normalizer import normalize
import json

def classify():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, content
        FROM articles_raw
        WHERE id NOT IN (SELECT raw_id FROM articles_scored)
    """)

    for raw_id, content in cur.fetchall():
        prompt = open("prompts/classify_weekly.txt").read()
        prompt = prompt.replace("{{content}}", normalize(content))

        response = call_llm(prompt)

        try:
            data = json.loads(response)
        except:
            continue

        cur.execute("""
            INSERT INTO articles_scored
            (raw_id, db_engine, topic, impact_score)
            VALUES (?, ?, ?, ?)
        """, (
            raw_id,
            data["db_engine"],
            data["topic"],
            data["impact_score"]
        ))

    conn.commit()
    conn.close()