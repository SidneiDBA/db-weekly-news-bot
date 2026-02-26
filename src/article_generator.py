from db import get_conn
from llm import call_llm
from datetime import date

def generate_weekly():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT r.title, r.url
        FROM articles_raw r
        JOIN articles_scored s ON s.raw_id = r.id
        WHERE s.impact_score >= 3
          AND s.is_duplicate = 0
        ORDER BY s.impact_score DESC
        LIMIT 7
    """)

    articles = cur.fetchall()
    articles_md = "\n".join([f"- {t} ({u})" for t, u in articles])

    prompt = open("prompts/weekly_article.txt").read()
    prompt = prompt.replace("{{articles}}", articles_md)
    prompt = prompt.replace("{{date}}", str(date.today()))

    md = call_llm(prompt)

    with open("output/weekly_brief.md", "w") as f:
        f.write(md)

    conn.close()