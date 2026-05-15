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


def normalize(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


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


def _ai_radar_topic_family(title, url):
    text = " ".join(filter(None, [title, url])).lower()

    if any(token in text for token in ["vector", "embedding", "embeddings", "semantic search", "similarity search", "retrieval", "rag", "index", "indexing"]):
        return "retrieval"
    if any(token in text for token in ["agent", "agents", "tool-using", "memory"]):
        return "agents"
    if any(token in text for token in ["monitoring", "observability", "debugging", "prometheus", "latency"]):
        return "observability"
    if any(token in text for token in ["foundation model", "foundation models", "training", "inference", "compute", "gpu", "serving"]):
        return "inference"
    if any(token in text for token in ["lakehouse", "sql", "database", "databases", "storage engine", "storage"]):
        return "data_platform"
    return "general_ai"


def _build_ai_radar_fallback_items(articles, section):
    items = []

    for title, url in articles:
        canonical_url = _canonicalize_url(url)
        topic_family = _ai_radar_topic_family(title, canonical_url)

        if section == "architecture":
            templates = {
                "retrieval": f"{title} shows how retrieval and indexing design may need to change for AI-assisted database workloads ({canonical_url}).",
                "agents": f"{title} highlights agent runtime and memory patterns that can affect orchestration around data systems ({canonical_url}).",
                "observability": f"{title} points to infrastructure visibility requirements for operating AI services alongside database platforms ({canonical_url}).",
                "inference": f"{title} signals compute and serving architecture decisions that shape AI features near data platforms ({canonical_url}).",
                "data_platform": f"{title} connects AI capabilities with database or lakehouse architecture decisions that can impact day-to-day platform design ({canonical_url}).",
                "general_ai": f"{title} indicates an AI infrastructure change worth mapping to current database-platform architecture ({canonical_url}).",
            }
        elif section == "cost":
            templates = {
                "retrieval": f"{title} can affect indexing density, retrieval latency, and storage cost for vector-heavy workloads ({canonical_url}).",
                "agents": f"{title} may change orchestration overhead and operational cost when agent flows touch production data systems ({canonical_url}).",
                "observability": f"{title} suggests more investment in telemetry and troubleshooting to keep AI infrastructure costs predictable ({canonical_url}).",
                "inference": f"{title} has implications for compute efficiency, throughput, and inference spend in AI-enabled data stacks ({canonical_url}).",
                "data_platform": f"{title} may shift scalability tradeoffs between AI services and the underlying database or lakehouse platform ({canonical_url}).",
                "general_ai": f"{title} should be reviewed for cost and scaling impact before adoption in production data environments ({canonical_url}).",
            }
        else:
            templates = {
                "retrieval": f"{title} needs validation around recall quality, index maintenance, and rollout safety before production use ({canonical_url}).",
                "agents": f"{title} raises readiness questions around guardrails, failure handling, and secure access to production data ({canonical_url}).",
                "observability": f"{title} improves production readiness only if monitoring and debugging workflows are mature enough for incident response ({canonical_url}).",
                "inference": f"{title} depends on mature serving, capacity planning, and operational controls before it is production-safe ({canonical_url}).",
                "data_platform": f"{title} should be checked for integration maturity, governance, and operational fit with existing data platforms ({canonical_url}).",
                "general_ai": f"{title} still needs a clear maturity and operational-readiness review before production rollout ({canonical_url}).",
            }

        items.append(templates[topic_family])

    return items


def _cloud_vendor_topic_family(title, url):
    text = " ".join(filter(None, [title, url])).lower()

    if any(token in text for token in ["aws", "azure", "google cloud", "gcp", "oracle", "oci", "huawei", "huaweicloud", "cloud sql", "dynamodb", "aurora", "cosmos", "bigquery", "spanner", "autonomous database", "gaussdb"]):
        return "managed_db"
    if any(token in text for token in ["snowflake", "databricks", "lakehouse", "storage", "s3", "gcs", "blob", "object storage", "iceberg", "delta"]):
        return "storage_platform"
    if any(token in text for token in ["ai", "llm", "model", "embedding", "rag", "retrieval", "inference", "vector"]):
        return "ai_services"
    if any(token in text for token in ["monitoring", "observability", "security", "governance", "latency", "cost"]):
        return "operations"
    return "general_cloud"


def _build_cloud_vendor_fallback_items(articles, section):
    items = []

    for title, url in articles:
        canonical_url = _canonicalize_url(url)
        topic_family = _cloud_vendor_topic_family(title, canonical_url)

        if section == "architecture":
            templates = {
                "managed_db": f"{title} affects how managed database services should be positioned across cloud architectures and service boundaries ({canonical_url}).",
                "storage_platform": f"{title} highlights storage and lakehouse design choices that can reshape data platform architecture on major cloud vendors ({canonical_url}).",
                "ai_services": f"{title} shows how vendor AI services can influence database-adjacent architectures, retrieval flows, and model-serving patterns ({canonical_url}).",
                "operations": f"{title} points to operational architecture changes needed to run cloud database and AI services reliably at scale ({canonical_url}).",
                "general_cloud": f"{title} signals a cloud-vendor platform change worth mapping into database, storage, and AI architecture plans ({canonical_url}).",
            }
        elif section == "cost":
            templates = {
                "managed_db": f"{title} can change service-tier, elasticity, and managed database cost tradeoffs across cloud providers ({canonical_url}).",
                "storage_platform": f"{title} has implications for storage growth, query efficiency, and platform spend in cloud data estates ({canonical_url}).",
                "ai_services": f"{title} may affect inference, retrieval, and managed AI service costs tied to cloud database workloads ({canonical_url}).",
                "operations": f"{title} suggests ongoing spend in observability, security, or operations needed to keep vendor platforms efficient ({canonical_url}).",
                "general_cloud": f"{title} should be reviewed for scaling and cost impact before adoption in cloud database environments ({canonical_url}).",
            }
        else:
            templates = {
                "managed_db": f"{title} needs validation around service maturity, migration fit, and operational readiness before production rollout ({canonical_url}).",
                "storage_platform": f"{title} should be checked for production fit, governance, and recovery implications in cloud storage platforms ({canonical_url}).",
                "ai_services": f"{title} depends on mature controls for model operations, retrieval quality, and vendor integration before production use ({canonical_url}).",
                "operations": f"{title} raises readiness questions around monitoring, incident response, and secure operation of vendor-managed services ({canonical_url}).",
                "general_cloud": f"{title} still needs a clear operational-readiness review before it belongs in production cloud data platforms ({canonical_url}).",
            }

        items.append(templates[topic_family])

    return items


def _cloud_vendor_solution_family(title, url):
    text = " ".join(filter(None, [title, url])).lower()

    if any(token in text for token in [
        "database",
        "databases",
        "sql",
        "cloud sql",
        "alloydb",
        "spanner",
        "dynamodb",
        "cosmos",
        "autonomous database",
        "gaussdb",
        "lakehouse",
        "warehouse",
        "storage",
        "object storage",
        "iceberg",
        "delta",
    ]):
        return "database"
    if any(token in text for token in [
        "ai",
        "llm",
        "model",
        "embedding",
        "rag",
        "retrieval",
        "vector",
        "inference",
        "agent",
        "agents",
        "machine learning",
    ]):
        return "ai"
    return "database"


def _build_cloud_vendor_solution_items(articles, solution):
    items = []

    for title, url in articles:
        canonical_url = _canonicalize_url(url)
        family = _cloud_vendor_solution_family(title, canonical_url)

        if solution == "database":
            if family == "ai":
                continue
            items.append(
                f"{title} highlights a cloud-vendor database or storage capability that can affect platform selection, integration patterns, or managed service design ({canonical_url})."
            )
        else:
            if family != "ai":
                continue
            items.append(
                f"{title} surfaces an AI-related cloud capability that may influence retrieval, model serving, or database-adjacent AI architecture ({canonical_url})."
            )

    return items


def _normalized_list_signature(items):
    return tuple(re.sub(r"\s+", " ", item.strip().lower()) for item in items if item.strip())


def _growth_family_for_article(title, url, report_mode):
    title = normalize(title)
    if report_mode == "ai_radar":
        return _ai_radar_topic_family(title, url)
    if report_mode == "cloud_vendor_radar":
        return _cloud_vendor_topic_family(title, url)
    return _weekly_bucket_for_article("", title, url)


def _production_signal_for_article(title, url, report_mode):
    title = normalize(title)
    text = " ".join(filter(None, [title, url])).lower()

    if any(token in text for token in ["beta", "preview", "research", "agent", "frontier", "prototype"]):
        label = "Experimental"
    elif any(token in text for token in ["integration", "lakehouse", "vector", "rag", "inference", "observability"]):
        label = "Watch closely"
    elif any(token in text for token in ["managed", "storage", "sql", "database", "backup", "replication", "governance"]):
        label = "Usable"
    else:
        label = "Watch closely"

    family = _growth_family_for_article(title, url, report_mode)
    reason_map = {
        "postgresql": "it touches proven operational patterns but still deserves workload-specific validation",
        "sql_server": "it affects established database operations and should be checked against current standards",
        "mysql_mariadb": "it can be adopted in familiar environments once backup, upgrade, and rollback paths are clear",
        "nosql": "distributed behavior and consistency tradeoffs need environment-specific testing",
        "analytics": "data-platform benefits are real, but integration and cost controls matter before rollout",
        "streaming": "pipeline dependencies and failure handling should be tested before production adoption",
        "general_db": "the operational path is plausible, but validation should come before rollout",
        "retrieval": "retrieval quality, indexing, and latency should be proven before production use",
        "agents": "guardrails and secure data access need more validation before broad use",
        "observability": "operational value is high if monitoring and incident response are already mature",
        "inference": "capacity, serving stability, and spend need to be tested on real workloads",
        "data_platform": "integration quality and governance maturity determine whether it is production-ready",
        "general_ai": "the concept is useful, but operational controls need to catch up",
        "managed_db": "migration fit and service limits should be validated against current operational standards",
        "storage_platform": "adoption depends on data layout, governance, and recovery planning",
        "ai_services": "model operations and data access controls should be tested before production rollout",
        "operations": "it is useful if the team can support the monitoring and incident workflow it requires",
        "general_cloud": "it deserves closer review before it changes a stable production platform",
    }

    return (
        f"{label}: {reason_map.get(family, 'it still needs a clear fit, test plan, and rollback path')}. "
        f"Reference item: {title} ({_canonicalize_url(url)})."
    )


def _build_growth_items(articles, report_mode, section):
    items = []
    for title, url in articles[:3]:
        title = normalize(title)
        canonical_url = _canonicalize_url(url)
        family = _growth_family_for_article(title, canonical_url, report_mode)

        if section == "care":
            templates = {
                "postgresql": f"{title} matters because PostgreSQL-style changes often affect indexing, replication, or query behavior that DBAs support directly ({canonical_url}).",
                "sql_server": f"{title} matters because SQL Server platform changes can alter maintenance, tuning, or service expectations in production ({canonical_url}).",
                "mysql_mariadb": f"{title} matters because MySQL and MariaDB operations usually surface through upgrades, compatibility, or performance work ({canonical_url}).",
                "nosql": f"{title} matters because distributed data systems change operational expectations around scaling, consistency, and troubleshooting ({canonical_url}).",
                "analytics": f"{title} matters because analytics and lakehouse tooling increasingly affects the DBA boundary around storage, governance, and performance ({canonical_url}).",
                "streaming": f"{title} matters because streaming platforms now influence ingestion reliability, latency, and downstream database behavior ({canonical_url}).",
                "general_db": f"{title} matters because it can change the practical work a DBA does around reliability, tuning, or platform selection ({canonical_url}).",
                "retrieval": f"{title} matters because retrieval and indexing quality now shape how AI features touch production data systems ({canonical_url}).",
                "agents": f"{title} matters because agent workflows increase pressure on permissions, observability, and safe access to operational data ({canonical_url}).",
                "observability": f"{title} matters because better monitoring is one of the fastest ways a junior DBA can reduce operational risk ({canonical_url}).",
                "inference": f"{title} matters because AI serving and GPU-backed workloads increasingly sit next to core data-platform operations ({canonical_url}).",
                "data_platform": f"{title} matters because AI and data-platform boundaries are merging, and DBAs need to understand the operational tradeoffs ({canonical_url}).",
                "general_ai": f"{title} matters because AI platform changes now affect database architecture, support models, and production operations ({canonical_url}).",
                "managed_db": f"{title} matters because managed vendor database features can change how DBAs think about service boundaries, support, and migration risk ({canonical_url}).",
                "storage_platform": f"{title} matters because storage-platform decisions affect performance, governance, and recovery strategy across data estates ({canonical_url}).",
                "ai_services": f"{title} matters because vendor AI services increasingly depend on data-platform design, access patterns, and governance ({canonical_url}).",
                "operations": f"{title} matters because operations maturity is often the difference between a useful platform feature and an incident source ({canonical_url}).",
                "general_cloud": f"{title} matters because cloud platform changes can quietly reshape database responsibilities and service expectations ({canonical_url}).",
            }
        elif section == "fit":
            templates = {
                "postgresql": f"{title} fits teams running transactional systems, replication-heavy estates, or performance-sensitive PostgreSQL services ({canonical_url}).",
                "sql_server": f"{title} fits SQL Server environments that depend on predictable maintenance, compatibility, and enterprise support models ({canonical_url}).",
                "mysql_mariadb": f"{title} fits operational teams managing common web, SaaS, or mixed open-source relational workloads ({canonical_url}).",
                "nosql": f"{title} fits high-scale distributed applications where consistency, shard design, or ingestion throughput matters ({canonical_url}).",
                "analytics": f"{title} fits lakehouse, warehouse, and mixed analytics environments where storage layout and governance are shared concerns ({canonical_url}).",
                "streaming": f"{title} fits event-driven systems where ingestion latency and downstream persistence need to stay predictable ({canonical_url}).",
                "general_db": f"{title} fits teams evaluating practical platform changes rather than purely academic or vendor-marketing claims ({canonical_url}).",
                "retrieval": f"{title} fits teams building RAG, semantic search, or AI features that depend on reliable retrieval quality ({canonical_url}).",
                "agents": f"{title} fits environments experimenting with workflow automation or tool-using AI against operational datasets ({canonical_url}).",
                "observability": f"{title} fits teams trying to mature monitoring, incident response, and troubleshooting around AI or data workloads ({canonical_url}).",
                "inference": f"{title} fits organizations running model-serving, fine-tuning, or GPU-backed platform services ({canonical_url}).",
                "data_platform": f"{title} fits data-platform teams responsible for both analytical infrastructure and AI-adjacent workloads ({canonical_url}).",
                "general_ai": f"{title} fits teams mapping AI capabilities to concrete platform responsibilities and support boundaries ({canonical_url}).",
                "managed_db": f"{title} fits teams evaluating managed database adoption, migration, or multi-vendor service tradeoffs ({canonical_url}).",
                "storage_platform": f"{title} fits storage-heavy environments with lakehouse, warehouse, or object-store coordination needs ({canonical_url}).",
                "ai_services": f"{title} fits data teams adopting vendor AI services that must coexist with governed production data ({canonical_url}).",
                "operations": f"{title} fits teams that need stronger operational discipline before scaling vendor-managed services ({canonical_url}).",
                "general_cloud": f"{title} fits platform teams comparing vendor services across cloud operations, portability, and support models ({canonical_url}).",
            }
        elif section == "risks":
            templates = {
                "postgresql": f"{title} should be reviewed for upgrade complexity, query-plan changes, and replication side effects before adoption ({canonical_url}).",
                "sql_server": f"{title} should be reviewed for licensing, compatibility, and operational dependency on Microsoft-specific tooling ({canonical_url}).",
                "mysql_mariadb": f"{title} should be reviewed for version drift, tooling compatibility, and performance regression risk ({canonical_url}).",
                "nosql": f"{title} should be reviewed for consistency tradeoffs, operational blast radius, and troubleshooting complexity ({canonical_url}).",
                "analytics": f"{title} should be reviewed for governance gaps, cost surprises, and weak rollback paths across data-platform layers ({canonical_url}).",
                "streaming": f"{title} should be reviewed for downstream dependency risk, replay complexity, and incident recovery paths ({canonical_url}).",
                "general_db": f"{title} should be reviewed for migration, observability, and rollback risk before any production decision ({canonical_url}).",
                "retrieval": f"{title} should be reviewed for weak recall, bad indexing assumptions, and latency surprises in production ({canonical_url}).",
                "agents": f"{title} should be reviewed for permission sprawl, unsafe actions, and poor failure isolation ({canonical_url}).",
                "observability": f"{title} should be reviewed for alert quality, telemetry cost, and operational noise ({canonical_url}).",
                "inference": f"{title} should be reviewed for GPU spend, serving instability, and workload-placement mistakes ({canonical_url}).",
                "data_platform": f"{title} should be reviewed for governance gaps, data movement risk, and operational sprawl ({canonical_url}).",
                "general_ai": f"{title} should be reviewed for unclear production fit, weak controls, and high implementation cost ({canonical_url}).",
                "managed_db": f"{title} should be reviewed for vendor lock-in, migration friction, and service-limit surprises ({canonical_url}).",
                "storage_platform": f"{title} should be reviewed for data layout mistakes, recovery gaps, and access-pattern cost drift ({canonical_url}).",
                "ai_services": f"{title} should be reviewed for data exposure, model-governance gaps, and integration risk ({canonical_url}).",
                "operations": f"{title} should be reviewed for operational overhead, alert fatigue, and response-readiness gaps ({canonical_url}).",
                "general_cloud": f"{title} should be reviewed for portability risk, service sprawl, and unclear ownership boundaries ({canonical_url}).",
            }
        elif section == "test":
            templates = {
                "postgresql": f"Lab this week: test query plans, replication behavior, or backup and restore assumptions. Start with {title} ({canonical_url}).",
                "sql_server": f"Lab this week: test maintenance workflows, compatibility, and rollback steps in a non-production SQL Server environment. Start with {title} ({canonical_url}).",
                "mysql_mariadb": f"Lab this week: test upgrades, performance baselines, and configuration drift in a sandbox. Start with {title} ({canonical_url}).",
                "nosql": f"Lab this week: test shard behavior, failure handling, or consistency expectations before rollout. Start with {title} ({canonical_url}).",
                "analytics": f"Lab this week: test storage layout, governance controls, and query-cost patterns on realistic datasets. Start with {title} ({canonical_url}).",
                "streaming": f"Lab this week: test replay, backpressure, and downstream recovery behavior under load. Start with {title} ({canonical_url}).",
                "general_db": f"Lab this week: build a small check for performance, compatibility, or observability impact. Start with {title} ({canonical_url}).",
                "retrieval": f"Lab this week: test recall quality, retrieval latency, and index maintenance on a representative dataset. Start with {title} ({canonical_url}).",
                "agents": f"Lab this week: test permission boundaries, auditability, and failure handling before broader use. Start with {title} ({canonical_url}).",
                "observability": f"Lab this week: test alerts, dashboards, and troubleshooting workflows during a simulated incident. Start with {title} ({canonical_url}).",
                "inference": f"Lab this week: test throughput, cost, and serving stability with a controlled workload. Start with {title} ({canonical_url}).",
                "data_platform": f"Lab this week: test data movement, governance, and operational ownership boundaries in a lab. Start with {title} ({canonical_url}).",
                "general_ai": f"Lab this week: test how AI features interact with production data access and operational controls. Start with {title} ({canonical_url}).",
                "managed_db": f"Lab this week: test service limits, failover expectations, and migration steps before adoption. Start with {title} ({canonical_url}).",
                "storage_platform": f"Lab this week: test data layout, lifecycle rules, and recovery expectations on realistic workloads. Start with {title} ({canonical_url}).",
                "ai_services": f"Lab this week: test model access patterns, governance controls, and integration behavior with production-like data. Start with {title} ({canonical_url}).",
                "operations": f"Lab this week: run a small operational readiness exercise before trusting it in production. Start with {title} ({canonical_url}).",
                "general_cloud": f"Lab this week: test the operational fit before adding another vendor dependency to the stack. Start with {title} ({canonical_url}).",
            }
        elif section == "skills":
            templates = {
                "postgresql": f"Next skill to build: indexing, replication, and PostgreSQL performance diagnostics. Start from {title} ({canonical_url}).",
                "sql_server": f"Next skill to build: SQL Server maintenance, wait analysis, and recovery planning. Start from {title} ({canonical_url}).",
                "mysql_mariadb": f"Next skill to build: MySQL internals, tuning, and upgrade safety. Start from {title} ({canonical_url}).",
                "nosql": f"Next skill to build: consistency models, partitioning, and distributed troubleshooting. Start from {title} ({canonical_url}).",
                "analytics": f"Next skill to build: lakehouse formats, query engines, and data governance. Start from {title} ({canonical_url}).",
                "streaming": f"Next skill to build: streaming reliability, offsets, and event-driven recovery patterns. Start from {title} ({canonical_url}).",
                "general_db": f"Next skill to build: capacity planning, observability, and operational tradeoffs. Start from {title} ({canonical_url}).",
                "retrieval": f"Next skill to build: embeddings, ANN indexing, and retrieval-quality evaluation. Start from {title} ({canonical_url}).",
                "agents": f"Next skill to build: agent safety, tool permissions, and workflow observability. Start from {title} ({canonical_url}).",
                "observability": f"Next skill to build: telemetry design, SLOs, and incident response patterns. Start from {title} ({canonical_url}).",
                "inference": f"Next skill to build: model serving, throughput planning, and cost controls. Start from {title} ({canonical_url}).",
                "data_platform": f"Next skill to build: data platform architecture, governance, and cross-team ownership. Start from {title} ({canonical_url}).",
                "general_ai": f"Next skill to build: how AI capabilities interact with real production data systems. Start from {title} ({canonical_url}).",
                "managed_db": f"Next skill to build: managed database SLAs, limits, and migration patterns. Start from {title} ({canonical_url}).",
                "storage_platform": f"Next skill to build: object storage, table formats, and workload-aware data layout. Start from {title} ({canonical_url}).",
                "ai_services": f"Next skill to build: model governance, serving interfaces, and secure data integration. Start from {title} ({canonical_url}).",
                "operations": f"Next skill to build: production operations, observability, and service ownership. Start from {title} ({canonical_url}).",
                "general_cloud": f"Next skill to build: vendor tradeoffs, portability, and operational boundaries. Start from {title} ({canonical_url}).",
            }
        else:
            items.append(_production_signal_for_article(title, canonical_url, report_mode))
            continue

        items.append(templates.get(family, f"{title} is worth studying for its practical platform and operational implications ({canonical_url})."))

    return items


def _weekly_bucket_for_article(source_name, title, url):
    text = " ".join(filter(None, [source_name, title, url])).lower()

    if any(token in text for token in ["postgres", "postgresql", "pgagroal", "pgexporter", "pg_sorted_heap"]):
        return "postgresql"
    if any(token in text for token in ["sql server", "sqlserver", "brent ozar"]):
        return "sql_server"
    if any(token in text for token in ["mysql", "mariadb", "percona"]):
        return "mysql_mariadb"
    if any(token in text for token in ["mongodb", "redis", "neo4j", "dynamodb", "couchdb", "influx", "nosql"]):
        return "nosql"
    if any(token in text for token in ["redpanda", "confluent", "pulsar", "kafka", "stream"]):
        return "streaming"
    if any(token in text for token in ["snowflake", "databricks", "clickhouse", "duckdb", "starburst", "big data", "dbt", "fivetran", "iceberg", "parquet", "arrow", "datahub", "openmetadata", "monte carlo"]):
        return "analytics"
    return "general_db"


def _select_weekly_articles(candidates, limit=7):
    bucket_priority = [
        "postgresql",
        "sql_server",
        "mysql_mariadb",
        "nosql",
        "analytics",
        "streaming",
        "general_db",
    ]
    bucket_cap = {
        "postgresql": 2,
        "sql_server": 2,
        "mysql_mariadb": 2,
        "nosql": 2,
        "analytics": 2,
        "streaming": 2,
        "general_db": 2,
    }

    grouped = {bucket: [] for bucket in bucket_priority}
    for article in candidates:
        bucket = _weekly_bucket_for_article(article[2], article[0], article[1])
        grouped.setdefault(bucket, []).append(article)

    selected = []
    selected_urls = set()
    bucket_counts = {bucket: 0 for bucket in grouped}

    for bucket in bucket_priority:
        for article in grouped.get(bucket, []):
            if article[1] in selected_urls:
                continue
            selected.append(article)
            selected_urls.add(article[1])
            bucket_counts[bucket] += 1
            break
        if len(selected) >= limit:
            return selected[:limit]

    for article in candidates:
        bucket = _weekly_bucket_for_article(article[2], article[0], article[1])
        if article[1] in selected_urls:
            continue
        if bucket_counts.get(bucket, 0) >= bucket_cap.get(bucket, 2):
            continue
        selected.append(article)
        selected_urls.add(article[1])
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        if len(selected) >= limit:
            return selected[:limit]

    return selected[:limit]


def _count_weekly_buckets(articles):
    return len(
        {
            _weekly_bucket_for_article(source_name, title, url)
            for title, url, source_name, _ in articles
        }
    )


def _bucket_allowed_sources(source_names):
    bucketed = {}
    for source_name in source_names or []:
        bucket = _weekly_bucket_for_article(source_name, source_name, source_name)
        bucketed.setdefault(bucket, []).append(source_name)
    return bucketed


def _ai_radar_relevance_score(source_name, title, url):
    text = " ".join(filter(None, [source_name, title, url])).lower()

    strong_positive_tokens = [
        "vector",
        "embedding",
        "embeddings",
        "rag",
        "retrieval",
        "semantic search",
        "hybrid search",
        "llm",
        "model serving",
        "inference",
        "agent",
        "agents",
        "ai infrastructure",
        "gpu",
        "sql",
        "database",
        "databases",
        "storage engine",
        "index",
        "indexing",
        "query",
        "queries",
        "latency",
        "observability",
        "monitoring",
        "ann",
    ]
    weak_positive_tokens = [
        "foundation model",
        "foundation models",
        "fine-tuning",
        "finetuning",
        "multimodal",
        "prompt caching",
        "context window",
        "token",
        "tokens",
        "throughput",
        "pipeline",
        "evaluation",
    ]
    negative_tokens = [
        "talent transformation",
        "talent",
        "workforce",
        "career",
        "leadership",
        "executive",
        "marketing",
        "sales",
        "funding",
        "conference recap",
    ]

    score = 0
    score += sum(3 for token in strong_positive_tokens if token in text)
    score += sum(1 for token in weak_positive_tokens if token in text)
    score -= sum(3 for token in negative_tokens if token in text)

    if any(token in text for token in ["weaviate", "pinecone", "elastic", "postgres", "postgresql", "mongodb", "databricks", "openai", "google ai", "aws machine learning", "huggingface", "nvidia", "arxiv", "research"]):
        score += 1

    return score


def _ai_radar_bucket_for_article(source_name, title, url):
    text = " ".join(filter(None, [source_name, title, url])).lower()

    if any(token in text for token in ["arxiv", "research", "microsoft research"]):
        return "research"
    if any(token in text for token in ["openai", "google ai", "aws machine learning", "nvidia"]):
        return "foundation_ai"
    if any(token in text for token in ["weaviate", "pinecone", "elastic", "vector", "embedding", "rag"]):
        return "vector_retrieval"
    if any(token in text for token in ["databricks", "clickhouse", "redpanda", "confluent", "kafka"]):
        return "data_platform"
    if any(token in text for token in ["postgresql", "mongodb"]):
        return "database_engines"
    return "general_ai"


def _select_ai_radar_articles(candidates, limit=7):
    bucket_priority = [
        "research",
        "foundation_ai",
        "vector_retrieval",
        "data_platform",
        "database_engines",
        "general_ai",
    ]
    bucket_cap = {
        "research": 2,
        "foundation_ai": 2,
        "vector_retrieval": 2,
        "data_platform": 2,
        "database_engines": 2,
        "general_ai": 2,
    }

    grouped = {bucket: [] for bucket in bucket_priority}
    relevance_scores = {
        article[1]: _ai_radar_relevance_score(article[2], article[0], article[1])
        for article in candidates
    }
    for article in candidates:
        bucket = _ai_radar_bucket_for_article(article[2], article[0], article[1])
        grouped.setdefault(bucket, []).append(article)

    for bucket, articles in grouped.items():
        grouped[bucket] = sorted(
            articles,
            key=lambda article: (
                relevance_scores[article[1]],
                article[3],
            ),
            reverse=True,
        )

    prioritized_candidates = sorted(
        candidates,
        key=lambda article: (
            relevance_scores[article[1]],
            article[3],
        ),
        reverse=True,
    )

    selected = []
    selected_urls = set()
    bucket_counts = {bucket: 0 for bucket in grouped}

    for bucket in bucket_priority:
        for article in grouped.get(bucket, []):
            if article[1] in selected_urls:
                continue
            if relevance_scores[article[1]] <= 0:
                continue
            selected.append(article)
            selected_urls.add(article[1])
            bucket_counts[bucket] += 1
            break
        if len(selected) >= limit:
            return selected[:limit]

    for article in prioritized_candidates:
        bucket = _ai_radar_bucket_for_article(article[2], article[0], article[1])
        if article[1] in selected_urls:
            continue
        if relevance_scores[article[1]] <= 0:
            continue
        if bucket_counts.get(bucket, 0) >= bucket_cap.get(bucket, 2):
            continue
        selected.append(article)
        selected_urls.add(article[1])
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        if len(selected) >= limit:
            return selected[:limit]

    minimum_viable_count = min(limit, 3)
    if len(selected) >= minimum_viable_count:
        return selected[:limit]

    for article in prioritized_candidates:
        bucket = _ai_radar_bucket_for_article(article[2], article[0], article[1])
        if article[1] in selected_urls:
            continue
        if bucket_counts.get(bucket, 0) >= bucket_cap.get(bucket, 2):
            continue
        selected.append(article)
        selected_urls.add(article[1])
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        if len(selected) >= limit:
            return selected[:limit]

    return selected[:limit]


def _count_ai_radar_buckets(articles):
    return len(
        {
            _ai_radar_bucket_for_article(source_name, title, url)
            for title, url, source_name, _ in articles
        }
    )


def _bucket_ai_radar_sources(source_names):
    bucketed = {}
    for source_name in source_names or []:
        bucket = _ai_radar_bucket_for_article(source_name, source_name, source_name)
        bucketed.setdefault(bucket, []).append(source_name)
    return bucketed


def _cloud_vendor_bucket_for_article(source_name, title, url):
    text = " ".join(filter(None, [source_name, title, url])).lower()

    if any(token in text for token in ["aws", "amazon", "azure", "microsoft", "google cloud", "gcp", "oracle", "oci", "huawei", "huaweicloud"]):
        return "hyperscaler"
    if any(token in text for token in ["snowflake", "databricks", "clickhouse", "mongodb", "sql server", "dynamodb", "autonomous database", "gaussdb"]):
        return "data_platform"
    if any(token in text for token in ["storage", "lakehouse", "iceberg", "delta", "blob", "s3", "gcs"]):
        return "storage"
    if any(token in text for token in ["ai", "llm", "model", "embedding", "rag", "retrieval", "inference", "vector", "pinecone", "elastic"]):
        return "ai_services"
    if any(token in text for token in ["confluent", "redpanda", "stream", "kafka"]):
        return "streaming"
    return "general_cloud"


def _cloud_vendor_source_matches_article(source_name, title, url):
    text = " ".join(filter(None, [title, url])).lower()
    source_text = (source_name or "").lower()

    source_vendor_tokens = {
        "aws": ["aws", "amazon", "bedrock", "sagemaker", "dynamodb", "aurora", "nova", "quick", "s3"],
        "microsoft": ["azure", "microsoft", "sql server", "azure sql", "cosmos"],
        "google": ["google", "google cloud", "gcp", "gemini", "bigquery", "spanner", "alloydb", "tpu"],
        "oracle": ["oracle", "oci", "autonomous database"],
        "huawei": ["huawei", "huaweicloud", "gaussdb"],
        "snowflake": ["snowflake"],
        "databricks": ["databricks"],
    }

    for vendor_key, tokens in source_vendor_tokens.items():
        if vendor_key in source_text:
            return any(token in text for token in tokens)

    return True


def _cloud_vendor_relevance_score(source_name, title, url):
    text = " ".join(filter(None, [source_name, title, url])).lower()

    target_vendor_tokens = [
        "aws",
        "amazon",
        "azure",
        "microsoft",
        "google cloud",
        "gcp",
        "oracle",
        "oci",
        "huawei",
        "huaweicloud",
        "snowflake",
        "databricks",
    ]
    target_platform_tokens = [
        "aurora",
        "dynamodb",
        "azure sql",
        "sql server",
        "cosmos",
        "bigquery",
        "spanner",
        "alloydb",
        "autonomous database",
        "gaussdb",
        "lakehouse",
        "object storage",
        "blob",
        "s3",
        "gcs",
    ]
    technical_focus_tokens = [
        "database",
        "databases",
        "storage",
        "managed",
        "sql",
        "lakehouse",
        "warehouse",
        "vector",
        "embedding",
        "rag",
        "retrieval",
        "inference",
        "observability",
        "governance",
        "cost",
        "scalability",
        "performance",
        "throughput",
    ]

    strong_positive_tokens = [
        "aws",
        "azure",
        "google cloud",
        "gcp",
        "oracle",
        "oci",
        "huawei",
        "huaweicloud",
        "sql server",
        "dynamodb",
        "aurora",
        "bigquery",
        "spanner",
        "cosmos",
        "autonomous database",
        "gaussdb",
        "snowflake",
        "databricks",
        "lakehouse",
        "storage",
        "database",
        "databases",
        "managed",
        "vector",
        "embedding",
        "rag",
        "retrieval",
        "inference",
        "ai",
        "llm",
        "observability",
        "governance",
        "cost",
        "scalability",
    ]
    weak_positive_tokens = [
        "cloud",
        "analytics",
        "warehouse",
        "lake",
        "platform",
        "security",
        "latency",
        "performance",
        "throughput",
    ]
    negative_tokens = [
        "talent transformation",
        "talent",
        "workforce",
        "career",
        "leadership",
        "conference",
        "research",
        "paper",
        "clinical",
        "fraud detection",
        "marketing",
        "sales",
    ]

    score = 0
    score += sum(3 for token in strong_positive_tokens if token in text)
    score += sum(1 for token in weak_positive_tokens if token in text)
    score -= sum(3 for token in negative_tokens if token in text)

    named_vendor_count = sum(1 for token in target_vendor_tokens if token in text)
    platform_signal_count = sum(1 for token in target_platform_tokens if token in text)
    technical_focus_count = sum(1 for token in technical_focus_tokens if token in text)
    score += named_vendor_count * 4
    score += platform_signal_count * 2

    has_named_vendor = named_vendor_count > 0
    source_text = (source_name or "").lower()
    if (
        has_named_vendor
        and technical_focus_count > 0
        and any(token in source_text for token in target_vendor_tokens)
    ):
        score += 4

    if has_named_vendor and technical_focus_count == 0:
        score -= 6

    return score


def _select_cloud_vendor_articles(candidates, limit=7):
    bucket_priority = [
        "hyperscaler",
        "data_platform",
        "storage",
        "ai_services",
        "streaming",
        "general_cloud",
    ]
    bucket_cap = {bucket: 2 for bucket in bucket_priority}

    grouped = {bucket: [] for bucket in bucket_priority}
    relevance_scores = {
        article[1]: _cloud_vendor_relevance_score(article[2], article[0], article[1])
        for article in candidates
    }
    for article in candidates:
        bucket = _cloud_vendor_bucket_for_article(article[2], article[0], article[1])
        grouped.setdefault(bucket, []).append(article)

    for bucket, articles in grouped.items():
        grouped[bucket] = sorted(
            articles,
            key=lambda article: (
                relevance_scores[article[1]],
                article[3],
            ),
            reverse=True,
        )

    prioritized_candidates = sorted(
        candidates,
        key=lambda article: (
            relevance_scores[article[1]],
            article[3],
        ),
        reverse=True,
    )

    selected = []
    selected_urls = set()
    bucket_counts = {bucket: 0 for bucket in grouped}

    for bucket in bucket_priority:
        for article in grouped.get(bucket, []):
            if article[1] in selected_urls:
                continue
            if not _cloud_vendor_source_matches_article(article[2], article[0], article[1]):
                continue
            if relevance_scores[article[1]] <= 0:
                continue
            selected.append(article)
            selected_urls.add(article[1])
            bucket_counts[bucket] += 1
            break
        if len(selected) >= limit:
            return selected[:limit]

    for article in prioritized_candidates:
        bucket = _cloud_vendor_bucket_for_article(article[2], article[0], article[1])
        if article[1] in selected_urls:
            continue
        if not _cloud_vendor_source_matches_article(article[2], article[0], article[1]):
            continue
        if relevance_scores[article[1]] <= 0:
            continue
        if bucket_counts.get(bucket, 0) >= bucket_cap.get(bucket, 2):
            continue
        selected.append(article)
        selected_urls.add(article[1])
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        if len(selected) >= limit:
            return selected[:limit]

    minimum_viable_count = min(limit, 3)
    if len(selected) >= minimum_viable_count:
        return selected[:limit]

    for article in prioritized_candidates:
        bucket = _cloud_vendor_bucket_for_article(article[2], article[0], article[1])
        if article[1] in selected_urls:
            continue
        if not _cloud_vendor_source_matches_article(article[2], article[0], article[1]):
            continue
        if bucket_counts.get(bucket, 0) >= bucket_cap.get(bucket, 2):
            continue
        selected.append(article)
        selected_urls.add(article[1])
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        if len(selected) >= limit:
            return selected[:limit]

    return selected[:limit]


def _count_cloud_vendor_buckets(articles):
    return len(
        {
            _cloud_vendor_bucket_for_article(source_name, title, url)
            for title, url, source_name, _ in articles
        }
    )


def _bucket_cloud_vendor_sources(source_names):
    bucketed = {}
    for source_name in source_names or []:
        bucket = _cloud_vendor_bucket_for_article(source_name, source_name, source_name)
        bucketed.setdefault(bucket, []).append(source_name)
    return bucketed


def _format_weekly_template(md_text, articles, source_urls):
    article_lines = []
    for index, (title, url) in enumerate(articles, start=1):
        title = normalize(title)
        article_lines.append(f"### {index}. {title}\n{_canonicalize_url(url)}")

    trends = _extract_list_items(_extract_section(md_text, ["trends observed", "trends"]))
    if not trends:
        trends = [normalize(title) for title, _ in articles]

    why_this_matters = _extract_list_items(_extract_section(md_text, ["why a dba should care", "why this matters", "why this matter"]))
    where_this_fits = _extract_list_items(_extract_section(md_text, ["where this fits", "fit"]))
    operational_risks = _extract_list_items(_extract_section(md_text, ["operational risks", "risks"]))
    test_this_week = _extract_list_items(_extract_section(md_text, ["what to test this week", "test this week", "what to test"]))
    skills_to_learn = _extract_list_items(_extract_section(md_text, ["skills to learn next", "skills", "learn next"]))
    production_signal = _extract_list_items(_extract_section(md_text, ["production signal", "maturity signal", "production readiness"]))

    if not why_this_matters:
        why_this_matters = _build_growth_items(articles, "weekly", "care") or [
            "Tracks the database and data-platform changes most likely to affect production operations.",
            "Helps prioritize follow-up investigation on tools, compatibility, and operational risk.",
            "Keeps DBA teams aligned on practical developments across the current article set.",
        ]
    if not where_this_fits:
        where_this_fits = _build_growth_items(articles, "weekly", "fit")
    if not operational_risks:
        operational_risks = _build_growth_items(articles, "weekly", "risks")
    if not test_this_week:
        test_this_week = _build_growth_items(articles, "weekly", "test")
    if not skills_to_learn:
        skills_to_learn = _build_growth_items(articles, "weekly", "skills")
    if not production_signal:
        production_signal = _build_growth_items(articles, "weekly", "signal")

    sources_block = _build_sources_block(source_urls)

    return (
        "\n\n".join(article_lines)
        + "\n\n## Trends Observed:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(trends, start=1))
        + "\n\n## Why A DBA Should Care:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(why_this_matters, start=1))
        + "\n\n## Where This Fits:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(where_this_fits, start=1))
        + "\n\n## Operational Risks:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(operational_risks, start=1))
        + "\n\n## What To Test This Week:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(test_this_week, start=1))
        + "\n\n## Skills To Learn Next:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(skills_to_learn, start=1))
        + "\n\n## Production Signal:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(production_signal, start=1))
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
    why_this_matters = _extract_list_items(_extract_section(md_text, ["why a dba should care", "why this matters"]))
    operational_risks = _extract_list_items(_extract_section(md_text, ["operational risks", "production readiness", "risks", "blockers"]))
    test_this_week = _extract_list_items(_extract_section(md_text, ["what to test this week", "recommended actions", "actions", "what to test"]))
    skills_to_learn = _extract_list_items(_extract_section(md_text, ["skills to learn next", "skills", "learn next"]))
    production_signal = _extract_list_items(_extract_section(md_text, ["production signal", "maturity signal", "production readiness"]))

    architecture_fallback = _build_ai_radar_fallback_items(articles, "architecture")
    cost_fallback = _build_ai_radar_fallback_items(articles, "cost")
    risks_fallback = _build_ai_radar_fallback_items(articles, "production")
    care_fallback = _build_growth_items(articles, "ai_radar", "care")
    test_fallback = _build_growth_items(articles, "ai_radar", "test")
    skills_fallback = _build_growth_items(articles, "ai_radar", "skills")
    signal_fallback = _build_growth_items(articles, "ai_radar", "signal")

    architecture_signature = _normalized_list_signature(architecture)
    cost_signature = _normalized_list_signature(cost)
    production_signature = _normalized_list_signature(operational_risks)
    repeated_sections = (
        architecture_signature
        and architecture_signature == cost_signature == production_signature
    )

    if not architecture:
        architecture = architecture_fallback
    if not cost:
        cost = cost_fallback
    if not why_this_matters:
        why_this_matters = care_fallback
    if not operational_risks:
        operational_risks = risks_fallback
    if not test_this_week:
        test_this_week = test_fallback
    if not skills_to_learn:
        skills_to_learn = skills_fallback
    if not production_signal:
        production_signal = signal_fallback
    if repeated_sections:
        architecture = architecture_fallback
        cost = cost_fallback
        operational_risks = risks_fallback

    sources_block = _build_sources_block(source_urls)

    return (
        intro
        + "\n\n## 🧭 Architecture Implications:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(architecture, start=1))
        + "\n\n## 💸 Cost & Scalability Notes:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(cost, start=1))
        + "\n\n## 🎯 Why A DBA Should Care:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(why_this_matters, start=1))
        + "\n\n## ⚠️ Operational Risks:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(operational_risks, start=1))
        + "\n\n## 🧪 What To Test This Week:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(test_this_week, start=1))
        + "\n\n## 📚 Skills To Learn Next:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(skills_to_learn, start=1))
        + "\n\n## 🚦 Production Signal:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(production_signal, start=1))
        + "\n\n## 📎 Sources\n"
        + sources_block
        + "\n"
    )


def _format_cloud_vendor_template(md_text, articles, source_urls):
    intro = _paragraphize(_extract_section(md_text, ["high-impact signals", "summary", "cloud signals"]))
    if not intro:
        intro = (
            "This briefing tracks cloud-vendor database services, storage platforms, and AI-adjacent capabilities "
            "that can change architecture, scaling, and production operations for data teams."
        )

    database_solutions = _extract_list_items(_extract_section(md_text, ["database solutions", "database services", "database platforms"]))
    ai_solutions = _extract_list_items(_extract_section(md_text, ["ai solutions", "ai services", "ai platforms"]))
    where_this_fits = _extract_list_items(_extract_section(md_text, ["where this fits", "fit", "architecture implications", "architecture"]))
    operational_risks = _extract_list_items(_extract_section(md_text, ["operational risks", "production readiness", "risks", "blockers"]))
    test_this_week = _extract_list_items(_extract_section(md_text, ["what to test this week", "recommended actions", "actions", "what to test"]))
    skills_to_learn = _extract_list_items(_extract_section(md_text, ["skills to learn next", "skills", "learn next"]))
    production_signal = _extract_list_items(_extract_section(md_text, ["production signal", "maturity signal", "production readiness"]))

    database_fallback = _build_cloud_vendor_solution_items(articles, "database")
    ai_fallback = _build_cloud_vendor_solution_items(articles, "ai")
    fit_fallback = _build_growth_items(articles, "cloud_vendor_radar", "fit")
    risks_fallback = _build_growth_items(articles, "cloud_vendor_radar", "risks")
    test_fallback = _build_growth_items(articles, "cloud_vendor_radar", "test")
    skills_fallback = _build_growth_items(articles, "cloud_vendor_radar", "skills")
    signal_fallback = _build_growth_items(articles, "cloud_vendor_radar", "signal")

    architecture_signature = _normalized_list_signature(where_this_fits)
    cost_signature = _normalized_list_signature(operational_risks)
    production_signature = _normalized_list_signature(production_signal)
    repeated_sections = (
        architecture_signature
        and architecture_signature == cost_signature == production_signature
    )

    if not database_solutions:
        database_solutions = database_fallback or fit_fallback[:3]
    if not ai_solutions:
        ai_solutions = ai_fallback or fit_fallback[:3]
    if not where_this_fits:
        where_this_fits = fit_fallback
    if not operational_risks:
        operational_risks = risks_fallback
    if not test_this_week:
        test_this_week = test_fallback
    if not skills_to_learn:
        skills_to_learn = skills_fallback
    if not production_signal:
        production_signal = signal_fallback
    if repeated_sections:
        where_this_fits = fit_fallback
        operational_risks = risks_fallback
        production_signal = signal_fallback

    sources_block = _build_sources_block(source_urls)

    return (
        intro
        + "\n\n## 🗄️ Database Solutions:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(database_solutions, start=1))
        + "\n\n## 🤖 AI Solutions:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(ai_solutions, start=1))
        + "\n\n## 🧩 Where This Fits:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(where_this_fits, start=1))
        + "\n\n## ⚠️ Operational Risks:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(operational_risks, start=1))
        + "\n\n## 🧪 What To Test This Week:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(test_this_week, start=1))
        + "\n\n## 📚 Skills To Learn Next:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(skills_to_learn, start=1))
        + "\n\n## 🚦 Production Signal:\n"
        + "\n".join(f"{index}. {item}" for index, item in enumerate(production_signal, start=1))
        + "\n\n## 📎 Sources\n"
        + sources_block
        + "\n"
    )


def _normalize_report_template(md_text, report_mode, articles, source_urls):
    if report_mode == "ai_radar":
        return _format_ai_radar_template(md_text, articles, source_urls)
    if report_mode == "cloud_vendor_radar":
        return _format_cloud_vendor_template(md_text, articles, source_urls)
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

    def _fetch_weekly_articles(days_back):
        if not allowed_sources:
            return []

        bucket_priority = [
            "postgresql",
            "sql_server",
            "mysql_mariadb",
            "nosql",
            "analytics",
            "streaming",
            "general_db",
        ]
        bucketed_sources = _bucket_allowed_sources(allowed_sources)
        collected = []

        for bucket in bucket_priority:
            bucket_sources = bucketed_sources.get(bucket, [])
            if not bucket_sources:
                continue
            placeholders = ",".join(["%s" for _ in bucket_sources])
            query = f"""
                SELECT r.title, r.url, r.source, s.impact_score
                FROM articles_raw r
                JOIN articles_scored s ON s.raw_id = r.id
                WHERE s.impact_score >= %s
                  AND s.is_duplicate = FALSE
                  AND r.source IN ({placeholders})
                  AND r.ingested_at >= NOW() - INTERVAL '{days_back} days'
                ORDER BY s.impact_score DESC
                LIMIT 3
            """
            cur.execute(query, (min_score_threshold, *bucket_sources))
            collected.extend(cur.fetchall())

        placeholders = ",".join(["%s" for _ in allowed_sources])
        query = f"""
            SELECT r.title, r.url, r.source, s.impact_score
            FROM articles_raw r
            JOIN articles_scored s ON s.raw_id = r.id
            WHERE s.impact_score >= %s
              AND s.is_duplicate = FALSE
              AND r.source IN ({placeholders})
              AND r.ingested_at >= NOW() - INTERVAL '{days_back} days'
            ORDER BY s.impact_score DESC
            LIMIT 100
        """
        cur.execute(query, (min_score_threshold, *allowed_sources))
        collected.extend(cur.fetchall())

        deduped = []
        seen_urls = set()
        for row in collected:
            if row[1] in seen_urls:
                continue
            seen_urls.add(row[1])
            deduped.append(row)

        return _select_weekly_articles(deduped, limit=7)

    def _fetch_ai_radar_articles(days_back):
        if not allowed_sources:
            return []

        bucket_priority = [
            "research",
            "foundation_ai",
            "vector_retrieval",
            "data_platform",
            "database_engines",
            "general_ai",
        ]
        bucketed_sources = _bucket_ai_radar_sources(allowed_sources)
        collected = []

        for bucket in bucket_priority:
            bucket_sources = bucketed_sources.get(bucket, [])
            if not bucket_sources:
                continue
            placeholders = ",".join(["%s" for _ in bucket_sources])
            query = f"""
                SELECT r.title, r.url, r.source, s.impact_score
                FROM articles_raw r
                JOIN articles_scored s ON s.raw_id = r.id
                WHERE s.impact_score >= %s
                  AND s.is_duplicate = FALSE
                  AND r.source IN ({placeholders})
                  AND r.ingested_at >= NOW() - INTERVAL '{days_back} days'
                ORDER BY s.impact_score DESC
                LIMIT 3
            """
            cur.execute(query, (min_score_threshold, *bucket_sources))
            collected.extend(cur.fetchall())

        placeholders = ",".join(["%s" for _ in allowed_sources])
        query = f"""
            SELECT r.title, r.url, r.source, s.impact_score
            FROM articles_raw r
            JOIN articles_scored s ON s.raw_id = r.id
            WHERE s.impact_score >= %s
              AND s.is_duplicate = FALSE
              AND r.source IN ({placeholders})
              AND r.ingested_at >= NOW() - INTERVAL '{days_back} days'
            ORDER BY s.impact_score DESC
            LIMIT 100
        """
        cur.execute(query, (min_score_threshold, *allowed_sources))
        collected.extend(cur.fetchall())

        deduped = []
        seen_urls = set()
        for row in collected:
            if row[1] in seen_urls:
                continue
            seen_urls.add(row[1])
            deduped.append(row)

        return _select_ai_radar_articles(deduped, limit=7)

    def _fetch_cloud_vendor_articles(days_back):
        if not allowed_sources:
            return []

        bucket_priority = [
            "hyperscaler",
            "data_platform",
            "storage",
            "ai_services",
            "streaming",
            "general_cloud",
        ]
        bucketed_sources = _bucket_cloud_vendor_sources(allowed_sources)
        collected = []

        for bucket in bucket_priority:
            bucket_sources = bucketed_sources.get(bucket, [])
            if not bucket_sources:
                continue
            placeholders = ",".join(["%s" for _ in bucket_sources])
            query = f"""
                SELECT r.title, r.url, r.source, s.impact_score
                FROM articles_raw r
                JOIN articles_scored s ON s.raw_id = r.id
                WHERE s.impact_score >= %s
                  AND s.is_duplicate = FALSE
                  AND r.source IN ({placeholders})
                  AND r.ingested_at >= NOW() - INTERVAL '{days_back} days'
                ORDER BY s.impact_score DESC
                LIMIT 3
            """
            cur.execute(query, (min_score_threshold, *bucket_sources))
            collected.extend(cur.fetchall())

        placeholders = ",".join(["%s" for _ in allowed_sources])
        query = f"""
            SELECT r.title, r.url, r.source, s.impact_score
            FROM articles_raw r
            JOIN articles_scored s ON s.raw_id = r.id
            WHERE s.impact_score >= %s
              AND s.is_duplicate = FALSE
              AND r.source IN ({placeholders})
              AND r.ingested_at >= NOW() - INTERVAL '{days_back} days'
            ORDER BY s.impact_score DESC
            LIMIT 100
        """
        cur.execute(query, (min_score_threshold, *allowed_sources))
        collected.extend(cur.fetchall())

        deduped = []
        seen_urls = set()
        for row in collected:
            if row[1] in seen_urls:
                continue
            seen_urls.add(row[1])
            deduped.append(row)

        return _select_cloud_vendor_articles(deduped, limit=7)

    def _fetch_articles(days_back):
        if report_mode == "weekly":
            return _fetch_weekly_articles(days_back)
        if report_mode == "ai_radar":
            return _fetch_ai_radar_articles(days_back)
        if report_mode == "cloud_vendor_radar":
            return _fetch_cloud_vendor_articles(days_back)

        if allowed_sources:
            placeholders = ",".join(["%s" for _ in allowed_sources])
            query = f"""
                SELECT r.title, r.url, r.source, s.impact_score
                FROM articles_raw r
                JOIN articles_scored s ON s.raw_id = r.id
                WHERE s.impact_score >= %s
                  AND s.is_duplicate = FALSE
                  AND r.source IN ({placeholders})
                  AND r.ingested_at >= NOW() - INTERVAL '{days_back} days'
                    ORDER BY s.impact_score DESC
                    LIMIT 100
            """
            cur.execute(query, (min_score_threshold, *allowed_sources))
        else:
            cur.execute(f"""
                SELECT r.title, r.url, r.source, s.impact_score
                FROM articles_raw r
                JOIN articles_scored s ON s.raw_id = r.id
                WHERE s.impact_score >= %s
                  AND s.is_duplicate = FALSE
                  AND r.ingested_at >= NOW() - INTERVAL '{days_back} days'
                    ORDER BY s.impact_score DESC
                    LIMIT 100
            """, (min_score_threshold,))
        rows = cur.fetchall()
        if report_mode == "weekly":
            rows = _select_weekly_articles(rows, limit=7)
        elif report_mode == "cloud_vendor_radar":
            rows = _select_cloud_vendor_articles(rows, limit=7)
        else:
            rows = rows[:7]
        return rows

    # Try progressively wider windows until we have at least 3 articles
    articles = []
    search_windows = (30, 90, 365) if report_mode == "weekly" else (7, 14, 30, 90, 365)
    for days in search_windows:
        articles = _fetch_articles(days)
        if report_mode == "weekly":
            if len(articles) >= 5 and _count_weekly_buckets(articles) >= 4:
                break
        elif report_mode == "ai_radar":
            if len(articles) >= 5 and _count_ai_radar_buckets(articles) >= 4:
                break
        elif report_mode == "cloud_vendor_radar":
            if len(articles) >= 5 and _count_cloud_vendor_buckets(articles) >= 4:
                break
        elif len(articles) >= 3:
            break
    if not articles:
        # Final fallback: all time
        if allowed_sources:
            placeholders = ",".join(["%s" for _ in allowed_sources])
            cur.execute(f"""
                SELECT r.title, r.url, r.source, s.impact_score FROM articles_raw r
                JOIN articles_scored s ON s.raw_id = r.id
                WHERE s.impact_score >= %s AND s.is_duplicate = FALSE
                  AND r.source IN ({placeholders})
                    ORDER BY s.impact_score DESC LIMIT 100
            """, (min_score_threshold, *allowed_sources))
        else:
            cur.execute("""
                SELECT r.title, r.url, r.source, s.impact_score FROM articles_raw r
                JOIN articles_scored s ON s.raw_id = r.id
                WHERE s.impact_score >= %s AND s.is_duplicate = FALSE
                    ORDER BY s.impact_score DESC LIMIT 100
            """, (min_score_threshold,))
        articles = cur.fetchall()
        if report_mode == "weekly":
            articles = _select_weekly_articles(articles, limit=7)
        elif report_mode == "ai_radar":
            articles = _select_ai_radar_articles(articles, limit=7)
        elif report_mode == "cloud_vendor_radar":
            articles = _select_cloud_vendor_articles(articles, limit=7)
        else:
            articles = articles[:7]
    articles_md = "\n".join([f"- {t} ({u})" for t, u, _, _ in articles])
    source_urls = [u for _, u, _, _ in articles if u]
    template_articles = [(t, u) for t, u, _, _ in articles]

    # work with absolute paths so script can be run from anywhere
    prompt_file = {
        "weekly": "article_weekly.txt",
        "ai_radar": "article_ai_radar.txt",
        "cloud_vendor_radar": "article_cloud_vendor.txt",
    }.get(report_mode, "article_weekly.txt")
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
    md = _normalize_report_template(md, report_mode, template_articles, source_urls)
    md = _replace_sources_section(md, source_urls)

    # Create output directory if it doesn't exist
    output_dir = os.path.join(root, "output")
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = {
        "weekly": "weekly_brief.md",
        "ai_radar": "ai_radar_brief.md",
        "cloud_vendor_radar": "cloud_vendor_radar_brief.md",
    }.get(report_mode, "weekly_brief.md")
    with open(os.path.join(output_dir, output_file), "w") as f:
        f.write(md)

    conn.close()