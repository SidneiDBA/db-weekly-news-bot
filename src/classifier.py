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
import json
import re
import os

def normalize(text):
    """Normalize text by removing extra whitespace and cleaning up content."""
    if not text:
        return ""
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Strip leading/trailing whitespace
    text = text.strip()
    return text

def clamp01(value, default=0.5):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = default

    if numeric > 1.0 and numeric <= 5.0:
        numeric = numeric / 5.0

    return max(0.0, min(numeric, 1.0))

def match_keywords(content, tags):
    normalized_content = normalize(content).lower()
    if not tags:
        return 0.0

    matches = 0
    for tag in tags:
        if normalize(str(tag)).lower() in normalized_content:
            matches += 1

    return round(matches / len(tags), 3)

def calculate_score(article, domain, source, llm_analysis, mode="weekly"):
    domain_weight = domain["weight"]
    source_weight = source.get("weight", 0.5)

    keyword_score = match_keywords(article["content"], domain["tags"])
    llm_relevance = llm_analysis["relevance"]
    architectural_impact = llm_analysis["architectural_impact"]
    production_impact = llm_analysis["production_impact"]
    security_impact = llm_analysis.get("security_impact", 0.5)
    retrieval_complexity = llm_analysis.get("retrieval_complexity", 0.5)

    if mode == "ai_radar":
        final_score = (
            domain_weight * 0.20 +
            source_weight * 0.10 +
            keyword_score * 0.10 +
            llm_relevance * 0.20 +
            architectural_impact * 0.15 +
            production_impact * 0.10 +
            security_impact * 0.10 +
            retrieval_complexity * 0.05
        )
    else:
        final_score = (
            domain_weight * 0.25 +
            source_weight * 0.15 +
            keyword_score * 0.15 +
            llm_relevance * 0.20 +
            architectural_impact * 0.15 +
            production_impact * 0.10
        )

    if domain["weight"] == 1.0:
        final_score *= 1.15

    return round(min(final_score, 1.0), 3)

def load_v2_sources_config():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    config_path = os.path.join(root, "config", "sources.json")
    with open(config_path) as f:
        return json.load(f)

def build_source_lookup(config):
    lookup = {}
    default_weight = config.get("global", {}).get("default_weight", 0.5)

    for domain_name, domain in config.get("domains", {}).items():
        domain_cfg = {
            "name": domain_name,
            "weight": clamp01(domain.get("weight", default_weight), default=default_weight),
            "tags": domain.get("tags", [])
        }

        for source in domain.get("sources", []):
            source_cfg = {
                "name": source.get("name", "unknown"),
                "weight": clamp01(source.get("weight", default_weight), default=default_weight)
            }
            lookup[source_cfg["name"].lower()] = (domain_cfg, source_cfg)

    return lookup

def classify(allowed_sources=None, mode="weekly"):
    conn = get_conn()
    cur = conn.cursor()
    config = load_v2_sources_config()
    source_lookup = build_source_lookup(config)
    default_weight = clamp01(config.get("global", {}).get("default_weight", 0.5), default=0.5)

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    prompt_file = "classify_ai_radar.txt" if mode == "ai_radar" else "classify_weekly.txt"
    prompt_path = os.path.join(root, "prompts", prompt_file)

    if allowed_sources:
        placeholders = ",".join(["?" for _ in allowed_sources])
        query = f"""
            SELECT id, source, title, content
            FROM articles_raw
            WHERE id NOT IN (SELECT raw_id FROM articles_scored)
              AND source IN ({placeholders})
        """
        cur.execute(query, tuple(allowed_sources))
    else:
        cur.execute("""
            SELECT id, source, title, content
            FROM articles_raw
            WHERE id NOT IN (SELECT raw_id FROM articles_scored)
        """)

    for raw_id, source_name, title, content in cur.fetchall():
        prompt = open(prompt_path).read()
        prompt = prompt.replace("{{content}}", normalize(content))

        response = call_llm(prompt)

        try:
            llm_raw = json.loads(response)
        except Exception:
            continue

        domain_cfg, source_cfg = source_lookup.get(
            normalize(source_name).lower(),
            (
                {"name": "general", "weight": default_weight, "tags": []},
                {"name": source_name or "unknown", "weight": default_weight}
            )
        )

        llm_analysis = {
            "relevance": clamp01(llm_raw.get("relevance", 0.5), default=0.5),
            "architectural_impact": clamp01(llm_raw.get("architectural_impact", 0.5), default=0.5),
            "production_impact": clamp01(llm_raw.get("production_impact", 0.5), default=0.5),
            "security_impact": clamp01(llm_raw.get("security_impact", 0.5), default=0.5),
            "retrieval_complexity": clamp01(llm_raw.get("retrieval_complexity", 0.5), default=0.5)
        }

        article = {
            "title": title,
            "content": content or ""
        }

        impact_score = calculate_score(article, domain_cfg, source_cfg, llm_analysis, mode=mode)

        cur.execute("""
            INSERT INTO articles_scored
            (raw_id, db_engine, topic, impact_score)
            VALUES (?, ?, ?, ?)
        """, (
            raw_id,
            llm_raw.get("db_engine", "general"),
            llm_raw.get("topic", "tooling"),
            impact_score
        ))

    conn.commit()
    conn.close()