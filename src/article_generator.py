# db-weekly-news-bot - Automated weekly database engineering news briefing.
# Copyright (C) 2026 SidneiDBA
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

from db import get_conn
from llm import call_llm
from datetime import date
import os
import json

def generate_weekly(report_mode="weekly", allowed_sources=None):
    conn = get_conn()
    cur = conn.cursor()

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    config_path = os.path.join(root, "config", "sources.json")
    min_score_threshold = 0.6
    try:
        with open(config_path) as config_file:
            config = json.load(config_file)
            min_score_threshold = float(config.get("global", {}).get("min_score_threshold", 0.6))
    except Exception:
        min_score_threshold = 0.6

    if allowed_sources:
        placeholders = ",".join(["?" for _ in allowed_sources])
        query = f"""
            SELECT r.title, r.url
            FROM articles_raw r
            JOIN articles_scored s ON s.raw_id = r.id
            WHERE s.impact_score >= ?
              AND s.is_duplicate = 0
              AND r.source IN ({placeholders})
            ORDER BY s.impact_score DESC
            LIMIT 7
        """
        cur.execute(query, (min_score_threshold, *allowed_sources))
    else:
        cur.execute("""
            SELECT r.title, r.url
            FROM articles_raw r
            JOIN articles_scored s ON s.raw_id = r.id
            WHERE s.impact_score >= ?
              AND s.is_duplicate = 0
            ORDER BY s.impact_score DESC
            LIMIT 7
        """, (min_score_threshold,))

    articles = cur.fetchall()
    articles_md = "\n".join([f"- {t} ({u})" for t, u in articles])

    # work with absolute paths so script can be run from anywhere
    prompt_file = "article_ai_radar.txt" if report_mode == "ai_radar" else "article_weekly.txt"
    prompt_path = os.path.join(root, "prompts", prompt_file)
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
    
    output_file = "ai_radar_brief.md" if report_mode == "ai_radar" else "weekly_brief.md"
    with open(os.path.join(output_dir, output_file), "w") as f:
        f.write(md)

    conn.close()