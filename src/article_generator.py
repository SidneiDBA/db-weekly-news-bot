from db import get_conn
from llm import call_llm
from datetime import date
import os

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

    # work with absolute paths so script can be run from anywhere
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    prompt_path = os.path.join(root, "prompts", "article_weekly.txt")
    prompt = open(prompt_path).read()
    prompt = prompt.replace("{{articles}}", articles_md)
    prompt = prompt.replace("{{date}}", str(date.today()))

    md = call_llm(prompt)

    # if the model returned something that parses as JSON it's probably the
    # mock response (or an error) rather than a real markdown summary; in that
    # case we refuse to overwrite the existing brief.
    # if the output is valid JSON, treat as a failure (mock response)
    import json as _json
    try:
        _json.loads(md)
    except _json.JSONDecodeError:
        # not JSON → good, proceed
        pass
    else:
        # load succeeded and md was JSON
        raise ValueError("LLM returned JSON instead of markdown")

    # Create output directory if it doesn't exist
    output_dir = os.path.join(root, "output")
    os.makedirs(output_dir, exist_ok=True)
    
    with open(os.path.join(output_dir, "weekly_brief.md"), "w") as f:
        f.write(md)

    conn.close()