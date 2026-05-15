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


def coerce_label(value, default):
    if isinstance(value, str):
        normalized = normalize(value)
        return normalized or default

    if isinstance(value, (int, float, bool)):
        return str(value)

    if isinstance(value, list):
        for item in value:
            coerced = coerce_label(item, "")
            if coerced:
                return coerced
        return default

    if isinstance(value, dict):
        for key in ["name", "label", "value", "topic", "engine", "db_engine", "type"]:
            if key in value:
                coerced = coerce_label(value.get(key), "")
                if coerced:
                    return coerced
        compact = normalize(json.dumps(value, sort_keys=True))
        return compact or default

    return default


def coerce_identifier(value, default=0):
    if isinstance(value, bool):
        return int(value)

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    if isinstance(value, str):
        try:
            return int(value.strip())
        except (TypeError, ValueError):
            return default

    if isinstance(value, dict):
        for key in ["id", "raw_id", "value"]:
            if key in value:
                return coerce_identifier(value.get(key), default)

    if isinstance(value, list):
        for item in value:
            coerced = coerce_identifier(item, None)
            if coerced is not None:
                return coerced

    return default


def coerce_number(value, default=0.0):
    if isinstance(value, bool):
        return float(int(value))

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        try:
            return float(value.strip())
        except (TypeError, ValueError):
            return default

    if isinstance(value, dict):
        for key in ["score", "value", "impact_score"]:
            if key in value:
                return coerce_number(value.get(key), default)

    if isinstance(value, list):
        for item in value:
            coerced = coerce_number(item, None)
            if coerced is not None:
                return coerced

    return default

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
    elif mode == "cloud_vendor_radar":
        final_score = (
            domain_weight * 0.20 +
            source_weight * 0.15 +
            keyword_score * 0.10 +
            llm_relevance * 0.20 +
            architectural_impact * 0.15 +
            production_impact * 0.10 +
            security_impact * 0.05 +
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
    prompt_file = {
        "weekly": "classify_weekly.txt",
        "ai_radar": "classify_ai_radar.txt",
        "cloud_vendor_radar": "classify_cloud_vendor.txt",
    }.get(mode, "classify_weekly.txt")
    prompt_path = os.path.join(root, "prompts", prompt_file)

    if allowed_sources:
        placeholders = ",".join(["%s" for _ in allowed_sources])
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

    rows = cur.fetchall()
    max_per_run = int(os.environ.get("MAX_CLASSIFICATIONS_PER_RUN", "0") or "0")
    if max_per_run > 0:
        rows = rows[:max_per_run]

    total_rows = len(rows)
    processed = 0
    attempts = 0
    json_parse_failures = 0

    for raw_id, source_name, title, content in rows:
        attempts += 1
        prompt = open(prompt_path).read()
        prompt = prompt.replace("{{content}}", normalize(content))

        response = call_llm(prompt, response_format="json")

        try:
            llm_raw = json.loads(response)
        except Exception:
            json_parse_failures += 1
            if attempts % 25 == 0:
                failure_pct = (json_parse_failures / attempts) * 100
                print(
                    f"classifier progress: {processed}/{total_rows} "
                    f"(attempts={attempts}, json_parse_failures={json_parse_failures}, "
                    f"failure_rate={failure_pct:.1f}%)"
                )
            continue

        # Some model responses are JSON arrays; prefer the first object payload.
        if isinstance(llm_raw, list):
            llm_raw = next((item for item in llm_raw if isinstance(item, dict)), None)

        if not isinstance(llm_raw, dict):
            json_parse_failures += 1
            if attempts % 25 == 0:
                failure_pct = (json_parse_failures / attempts) * 100
                print(
                    f"classifier progress: {processed}/{total_rows} "
                    f"(attempts={attempts}, json_parse_failures={json_parse_failures}, "
                    f"failure_rate={failure_pct:.1f}%)"
                )
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
            VALUES (%s, %s, %s, %s)
        """, (
            coerce_identifier(raw_id),
            coerce_label(llm_raw.get("db_engine", "general"), "general"),
            coerce_label(llm_raw.get("topic", "tooling"), "tooling"),
            coerce_number(impact_score)
        ))

        processed += 1
        if attempts % 25 == 0:
            conn.commit()
            failure_pct = (json_parse_failures / attempts) * 100 if attempts else 0.0
            print(
                f"classifier progress: {processed}/{total_rows} "
                f"(attempts={attempts}, json_parse_failures={json_parse_failures}, "
                f"failure_rate={failure_pct:.1f}%)"
            )

    conn.commit()
    if total_rows:
        failure_pct = (json_parse_failures / attempts) * 100 if attempts else 0.0
        print(
            f"classifier completed: {processed}/{total_rows} "
            f"(attempts={attempts}, json_parse_failures={json_parse_failures}, "
            f"failure_rate={failure_pct:.1f}%)"
        )
    conn.close()