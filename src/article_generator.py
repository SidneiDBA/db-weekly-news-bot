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
import re


def _split_trailing_url_punctuation(url):
    suffix = ""
    while url and url[-1] in ".,;:!?":
        suffix = url[-1] + suffix
        url = url[:-1]
    return url, suffix


def _canonicalize_url(url):
    if not url:
        return url

    stackexchange_match = re.match(
        r"^(https?://[^/]*stackexchange\.com/questions/\d+)(?:/[^\s?#)]*)?.*$",
        url,
        flags=re.IGNORECASE,
    )
    if stackexchange_match:
        return stackexchange_match.group(1) + "/"

    return url


def _normalize_url_prefixes(md_text, source_urls):
    """Replace truncated URL prefixes in model output with exact source URLs."""
    if not md_text or not source_urls:
        return md_text

    normalized_sources = [_canonicalize_url(url) for url in source_urls]
    url_token_pattern = re.compile(r"https?://[^\s)]+")
    seen = set()

    def replace_token(match):
        token = match.group(0)
        normalized_token, suffix = _split_trailing_url_punctuation(token)
        if normalized_token in seen:
            return token
        seen.add(normalized_token)

        canonical_token = _canonicalize_url(normalized_token)
        if canonical_token in normalized_sources:
            return canonical_token + suffix

        matches = [full for full in normalized_sources if full.startswith(normalized_token)]
        if len(matches) == 1:
            return matches[0] + suffix
        return canonical_token + suffix

    return url_token_pattern.sub(replace_token, md_text)


def _remove_unknown_urls(md_text, source_urls):
    """Strip model-invented URLs so briefs only reference collected articles."""
    if not md_text or not source_urls:
        return md_text

    normalized_sources = [_canonicalize_url(url) for url in source_urls if url]
    url_token_pattern = re.compile(r"https?://[^\s)]+")

    def replace_token(match):
        token = match.group(0)
        normalized_token, suffix = _split_trailing_url_punctuation(token)
        canonical_token = _canonicalize_url(normalized_token)

        if canonical_token in normalized_sources:
            return canonical_token + suffix

        matches = [full for full in normalized_sources if full.startswith(normalized_token)]
        if len(matches) == 1:
            return matches[0] + suffix

        return suffix

    sanitized = url_token_pattern.sub(replace_token, md_text)
    sanitized = re.sub(r"\(\s*\)", "", sanitized)
    sanitized = re.sub(r"\bat\s+([.,;:!?])", r"\1", sanitized)
    sanitized = re.sub(r"\s+([.,;:!?])", r"\1", sanitized)
    return sanitized


def _replace_sources_section(md_text, source_urls):
    """Ensure the Sources section always contains complete, exact URLs."""
    if not source_urls:
        return md_text

    normalized_sources = []
    seen = set()
    for url in source_urls:
        normalized = _canonicalize_url(url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            normalized_sources.append(normalized)

    sources_block = "\n".join([f"- {url}" for url in normalized_sources])
    header_pattern = re.compile(r"^##\s+.*sources.*$", re.IGNORECASE | re.MULTILINE)
    header_match = header_pattern.search(md_text)

    if header_match:
        next_header_pattern = re.compile(r"^##\s+", re.MULTILINE)
        next_header_match = next_header_pattern.search(md_text, header_match.end())
        start = header_match.start()
        end = next_header_match.start() if next_header_match else len(md_text)
        normalized_section = f"## 📎 Sources\n{sources_block}\n"
        return md_text[:start] + normalized_section + md_text[end:]

    return md_text.rstrip() + f"\n\n## 📎 Sources\n{sources_block}\n"


def _extract_section(md_text, headings):
    pattern = re.compile(r"^##+\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(md_text or ""))
    lowered_targets = tuple(heading.lower() for heading in headings)

    for index, match in enumerate(matches):
        heading = match.group(1).strip().lower()
        if any(target in heading for target in lowered_targets):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(md_text)
            return md_text[start:end].strip()
    return ""


def _extract_list_items(section_text):
    items = []
    for line in (section_text or "").splitlines():
        cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)])\s+", "", line).strip()
        if cleaned:
            items.append(cleaned)
    return items


def _paragraphize(section_text):
    lines = [line.strip() for line in (section_text or "").splitlines() if line.strip()]
    if not lines:
        return ""
    return " ".join(lines)


def _build_sources_block(source_urls):
    normalized_sources = []
    seen = set()
    for url in source_urls:
        normalized = _canonicalize_url(url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            normalized_sources.append(normalized)
    return "\n".join([f"- {url}" for url in normalized_sources])


def _format_weekly_template(md_text, articles, source_urls):
    article_lines = []
    for index, (title, url) in enumerate(articles, start=1):
        article_lines.append(f"### {index}. {title}\n{_canonicalize_url(url)}")

    trends = _extract_list_items(_extract_section(md_text, ["trends observed", "trends"]))
    if not trends:
        trends = [title for title, _ in articles]

    why_this_matters = _extract_list_items(_extract_section(md_text, ["why this matters", "why this matter"]))
    if not why_this_matters:
        why_this_matters = [
            "Tracks the database and data-platform changes most likely to affect production operations.",
            "Helps prioritize follow-up investigation on tools, compatibility, and operational risk.",
            "Keeps DBA teams aligned on practical developments across the current article set.",
        ]

    sources_block = _build_sources_block(source_urls)

    return (
        "\n\n".join(article_lines)
        + "\n\n## Trends Observed:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(trends, start=1))
        + "\n\n## Why This Matters:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(why_this_matters, start=1))
        + "\n\n## 📎 Sources\n"
        + sources_block
        + "\n"
    )


def _format_ai_radar_template(md_text, articles, source_urls):
    intro = _paragraphize(_extract_section(md_text, ["high-impact signals", "summary"]))
    if not intro:
        intro = (
            "This compilation highlights the current state of AI infrastructures for databases, "
            "embedding technology, RAG, LLM-SQL combinations and their implications on storage engines."
        )

    architecture = _extract_list_items(_extract_section(md_text, ["architecture implications"]))
    cost = _extract_list_items(_extract_section(md_text, ["cost & scalability notes", "cost", "scalability"]))
    production = _extract_list_items(_extract_section(md_text, ["production readiness", "risks", "blockers"]))
    actions = _extract_list_items(_extract_section(md_text, ["recommended actions", "actions"]))

    fallback_items = [
        f"{title} ({_canonicalize_url(url)})" for title, url in articles
    ]

    if not architecture:
        architecture = fallback_items
    if not cost:
        cost = fallback_items
    if not production:
        production = fallback_items
    if not actions:
        actions = [
            "Review the linked articles for concrete architectural changes before adopting new AI-data patterns.",
            "Prioritize experiments that improve retrieval quality, indexing strategy, or production readiness.",
            "Track cost and operational impact for any LLM, vector, or RAG feature introduced into the platform.",
        ]

    sources_block = _build_sources_block(source_urls)

    return (
        intro
        + "\n\n## 🧭 Architecture Implications:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(architecture, start=1))
        + "\n\n## 💸 Cost & Scalability Notes:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(cost, start=1))
        + "\n\n## 🏭 Production Readiness:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(production, start=1))
        + "\n\n## 🛠️ Recommended Actions:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(actions, start=1))
        + "\n\n## 📎 Sources\n"
        + sources_block
        + "\n"
    )


def _normalize_report_template(md_text, report_mode, articles, source_urls):
    if report_mode == "ai_radar":
        return _format_ai_radar_template(md_text, articles, source_urls)
    return _format_weekly_template(md_text, articles, source_urls)

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

    def _fetch_articles(days_back):
        if allowed_sources:
            placeholders = ",".join(["%s" for _ in allowed_sources])
            query = f"""
                SELECT r.title, r.url
                FROM articles_raw r
                JOIN articles_scored s ON s.raw_id = r.id
                WHERE s.impact_score >= %s
                  AND s.is_duplicate = FALSE
                  AND r.source IN ({placeholders})
                  AND r.ingested_at >= NOW() - INTERVAL '{days_back} days'
                ORDER BY s.impact_score DESC
                LIMIT 7
            """
            cur.execute(query, (min_score_threshold, *allowed_sources))
        else:
            cur.execute(f"""
                SELECT r.title, r.url
                FROM articles_raw r
                JOIN articles_scored s ON s.raw_id = r.id
                WHERE s.impact_score >= %s
                  AND s.is_duplicate = FALSE
                  AND r.ingested_at >= NOW() - INTERVAL '{days_back} days'
                ORDER BY s.impact_score DESC
                LIMIT 7
            """, (min_score_threshold,))
        return cur.fetchall()

    # Try progressively wider windows until we have at least 3 articles
    articles = []
    for days in (7, 14, 30, 90, 365):
        articles = _fetch_articles(days)
        if len(articles) >= 3:
            break
    if not articles:
        # Final fallback: all time
        if allowed_sources:
            placeholders = ",".join(["%s" for _ in allowed_sources])
            cur.execute(f"""
                SELECT r.title, r.url FROM articles_raw r
                JOIN articles_scored s ON s.raw_id = r.id
                WHERE s.impact_score >= %s AND s.is_duplicate = FALSE
                  AND r.source IN ({placeholders})
                ORDER BY s.impact_score DESC LIMIT 7
            """, (min_score_threshold, *allowed_sources))
        else:
            cur.execute("""
                SELECT r.title, r.url FROM articles_raw r
                JOIN articles_scored s ON s.raw_id = r.id
                WHERE s.impact_score >= %s AND s.is_duplicate = FALSE
                ORDER BY s.impact_score DESC LIMIT 7
            """, (min_score_threshold,))
        articles = cur.fetchall()
    articles_md = "\n".join([f"- {t} ({u})" for t, u in articles])
    source_urls = [u for _, u in articles if u]

    # work with absolute paths so script can be run from anywhere
    prompt_file = "article_ai_radar.txt" if report_mode == "ai_radar" else "article_weekly.txt"
    prompt_path = os.path.join(root, "prompts", prompt_file)
    prompt = open(prompt_path).read()
    prompt = prompt.replace("{{articles}}", articles_md)
    prompt = prompt.replace("{{date}}", str(date.today()))

    md = call_llm(prompt, response_format="markdown")

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

    md = _normalize_url_prefixes(md, source_urls)
    md = _remove_unknown_urls(md, source_urls)
    md = _normalize_report_template(md, report_mode, articles, source_urls)
    md = _replace_sources_section(md, source_urls)

    # Create output directory if it doesn't exist
    output_dir = os.path.join(root, "output")
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = "ai_radar_brief.md" if report_mode == "ai_radar" else "weekly_brief.md"
    with open(os.path.join(output_dir, output_file), "w") as f:
        f.write(md)

    conn.close()