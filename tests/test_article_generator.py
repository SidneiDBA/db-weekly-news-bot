import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from article_generator import _ai_radar_relevance_score, _cloud_vendor_relevance_score, _cloud_vendor_source_matches_article, _extract_section, _normalize_report_template, _remove_unknown_urls, _select_ai_radar_articles, _select_cloud_vendor_articles, _select_weekly_articles


def test_remove_unknown_urls_keeps_only_collected_article_links():
    markdown = (
        "See the original source at https://example.com/real-article. "
        "Additionally, check the roundup at https://news.data-intensive.com/."
    )

    sanitized = _remove_unknown_urls(markdown, ["https://example.com/real-article"])

    assert "https://example.com/real-article" in sanitized
    assert "https://news.data-intensive.com/" not in sanitized


def test_remove_unknown_urls_keeps_trailing_punctuation_for_known_links():
    markdown = "Reference: https://example.com/real-article."

    sanitized = _remove_unknown_urls(markdown, ["https://example.com/real-article"])

    assert sanitized.endswith("https://example.com/real-article.")


def test_normalize_weekly_template_matches_reference_shape():
    markdown = """## 🔥 Top Updates This Week
- Trend one

## 🧠 Trends Observed
- Trend one
- Trend two

## 🎯 Why This Matters
- Reason one
- Reason two
"""

    normalized = _normalize_report_template(
        markdown,
        "weekly",
        [("Article One", "https://example.com/1"), ("Article Two", "https://example.com/2")],
        ["https://example.com/1", "https://example.com/2"],
    )

    assert "### 1. Article One" in normalized
    assert "## Trends Observed:" in normalized
    assert "## Why This Matters:" in normalized
    assert "## 📎 Sources" in normalized


def test_normalize_ai_radar_template_matches_reference_shape():
    markdown = """## 🚨 High-Impact Signals
AI systems are reshaping retrieval design.

## 🧭 Architecture Implications
- Architecture item

## 💸 Cost & Scalability Notes
- Cost item

## 🏭 Production Readiness
- Production item

## 🛠️ Recommended Actions
- Action item
"""

    normalized = _normalize_report_template(
        markdown,
        "ai_radar",
        [("Article One", "https://example.com/1")],
        ["https://example.com/1"],
    )

    assert normalized.startswith("AI systems are reshaping retrieval design.")
    assert "## 🧭 Architecture Implications:" in normalized
    assert "## 💸 Cost & Scalability Notes:" in normalized
    assert "## 🏭 Production Readiness:" in normalized
    assert "## 🛠️ Recommended Actions:" in normalized


def test_normalize_cloud_vendor_template_matches_reference_shape():
    markdown = """## ☁️ Cloud Signals
Cloud database services and storage platforms are shifting quickly.

## 🗄️ Database Solutions
- Database item

## 🤖 AI Solutions
- AI item

## 🧭 Architecture Implications
- Architecture item

## 💸 Cost & Scalability Notes
- Cost item

## 🏭 Production Readiness
- Production item

## 🛠️ Recommended Actions
- Action item
"""

    normalized = _normalize_report_template(
        markdown,
        "cloud_vendor_radar",
        [("Article One", "https://example.com/1")],
        ["https://example.com/1"],
    )

    assert normalized.startswith("Cloud database services and storage platforms are shifting quickly.")
    assert "## 🗄️ Database Solutions:" in normalized
    assert "## 🤖 AI Solutions:" in normalized
    assert "## 🧭 Architecture Implications:" in normalized
    assert "## 💸 Cost & Scalability Notes:" in normalized
    assert "## 🏭 Production Readiness:" in normalized
    assert "## 🛠️ Recommended Actions:" in normalized


def test_normalize_cloud_vendor_template_builds_database_and_ai_sections():
    normalized = _normalize_report_template(
        "",
        "cloud_vendor_radar",
        [
            ("Azure SQL managed storage improvements", "https://example.com/db"),
            ("Oracle AI inference for enterprise data", "https://example.com/ai"),
        ],
        [
            "https://example.com/db",
            "https://example.com/ai",
        ],
    )

    database = _extract_section(normalized, ["database solutions"])
    ai = _extract_section(normalized, ["ai solutions"])

    assert database
    assert ai
    assert "managed storage improvements" in database.lower()
    assert "inference" in ai.lower()


def test_normalize_ai_radar_template_builds_distinct_fallback_sections():
    normalized = _normalize_report_template(
        "",
        "ai_radar",
        [
            ("Vector indexing for RAG query latency", "https://example.com/vector"),
            ("Real-time monitoring for inference clusters", "https://example.com/monitoring"),
            ("Agent memory patterns for tool-using systems", "https://example.com/agents"),
        ],
        [
            "https://example.com/vector",
            "https://example.com/monitoring",
            "https://example.com/agents",
        ],
    )

    architecture = _extract_section(normalized, ["architecture implications"])
    cost = _extract_section(normalized, ["cost & scalability notes"])
    production = _extract_section(normalized, ["production readiness"])

    assert architecture
    assert cost
    assert production
    assert architecture != cost
    assert architecture != production
    assert cost != production


def test_normalize_ai_radar_template_replaces_repeated_model_sections():
    markdown = """## 🧭 Architecture Implications
- Same item one
- Same item two

## 💸 Cost & Scalability Notes
- Same item one
- Same item two

## 🏭 Production Readiness
- Same item one
- Same item two
"""

    normalized = _normalize_report_template(
        markdown,
        "ai_radar",
        [
            ("Vector indexing for RAG query latency", "https://example.com/vector"),
            ("Real-time monitoring for inference clusters", "https://example.com/monitoring"),
        ],
        [
            "https://example.com/vector",
            "https://example.com/monitoring",
        ],
    )

    architecture = _extract_section(normalized, ["architecture implications"])
    cost = _extract_section(normalized, ["cost & scalability notes"])
    production = _extract_section(normalized, ["production readiness"])

    assert "Same item one" not in architecture
    assert architecture != cost
    assert architecture != production


def test_select_cloud_vendor_articles_balances_vendor_families():
    candidates = [
        ("AWS Aurora storage update", "https://example.com/aws", "AWS Big Data", 0.95),
        ("Azure SQL elasticity", "https://example.com/azure", "Microsoft SQL Server Blog", 0.94),
        ("Databricks lakehouse governance", "https://example.com/dbx", "Databricks Engineering Blog", 0.93),
        ("Snowflake storage optimization", "https://example.com/snow", "Snowflake Blog", 0.92),
        ("Pinecone managed retrieval", "https://example.com/pine", "Pinecone Blog", 0.91),
        ("Confluent cloud streams", "https://example.com/stream", "Confluent Kafka Blog", 0.90),
    ]

    selected = _select_cloud_vendor_articles(candidates, limit=6)
    selected_sources = {row[2] for row in selected}

    assert "AWS Big Data" in selected_sources
    assert "Microsoft SQL Server Blog" in selected_sources
    assert "Databricks Engineering Blog" in selected_sources
    assert "Pinecone Blog" in selected_sources


def test_cloud_vendor_relevance_prefers_database_storage_ai_topics():
    strong_score = _cloud_vendor_relevance_score(
        "Databricks Engineering Blog",
        "Lakehouse storage optimization for managed AI inference",
        "https://example.com/lakehouse-ai",
    )
    weak_score = _cloud_vendor_relevance_score(
        "Databricks Engineering Blog",
        "Why talent transformation is the missing focus in enterprise AI",
        "https://example.com/talent-transformation",
    )

    assert strong_score > weak_score


def test_select_cloud_vendor_articles_deprioritizes_generic_vendor_posts():
    candidates = [
        (
            "Why talent transformation is the missing focus in enterprise AI",
            "https://www.databricks.com/blog/why-talent-transformation-missing-focus-enterprise-ai",
            "Databricks Engineering Blog",
            0.98,
        ),
        (
            "Lakehouse storage optimization for managed AI inference",
            "https://www.databricks.com/blog/lakehouse-storage-optimization-managed-ai-inference",
            "Databricks Engineering Blog",
            0.91,
        ),
        ("AWS Aurora scaling", "https://example.com/aws", "AWS Big Data", 0.93),
        ("Cloud SQL vector search", "https://example.com/gcp", "Google Cloud Blog", 0.92),
        ("Pinecone managed retrieval", "https://example.com/pine", "Pinecone Blog", 0.90),
    ]

    selected = _select_cloud_vendor_articles(candidates, limit=4)
    selected_urls = {row[1] for row in selected}

    assert "https://www.databricks.com/blog/lakehouse-storage-optimization-managed-ai-inference" in selected_urls
    assert "https://www.databricks.com/blog/why-talent-transformation-missing-focus-enterprise-ai" not in selected_urls


def test_cloud_vendor_relevance_prefers_named_vendor_updates_over_generic_platform_posts():
    named_vendor_score = _cloud_vendor_relevance_score(
        "Huawei Cloud Updates",
        "Huawei Cloud GaussDB storage improvements for AI workloads",
        "https://example.com/huawei-gaussdb",
    )
    generic_platform_score = _cloud_vendor_relevance_score(
        "Starburst Blog",
        "AI data governance for enterprise platforms",
        "https://example.com/generic-ai-governance",
    )

    assert named_vendor_score > generic_platform_score


def test_cloud_vendor_source_match_rejects_stale_miswired_vendor_rows():
    assert not _cloud_vendor_source_matches_article(
        "Databricks Blog",
        "Starburst Integrates with Google Cloud's Lakehouse",
        "https://www.starburst.io/blog/starburst-integrates-with-google-cloud-lakehouse",
    )
    assert _cloud_vendor_source_matches_article(
        "Databricks Blog",
        "AI Gateway governance layer for agentic AI",
        "https://www.databricks.com/blog/ai-gateway-governance-layer-agentic-ai",
    )


def test_select_cloud_vendor_articles_drops_miswired_vendor_backlog_rows():
    candidates = [
        (
            "Starburst Integrates with Google Cloud's Lakehouse",
            "https://www.starburst.io/blog/starburst-integrates-with-google-cloud-lakehouse",
            "Databricks Blog",
            0.98,
        ),
        (
            "AI Gateway governance layer for agentic AI",
            "https://www.databricks.com/blog/ai-gateway-governance-layer-agentic-ai",
            "Databricks Blog",
            0.92,
        ),
        (
            "Oracle Database and Snowflake AI Data Cloud integration",
            "https://example.com/oracle-snowflake",
            "Snowflake Blog",
            0.91,
        ),
    ]

    selected = _select_cloud_vendor_articles(candidates, limit=3)
    selected_urls = {row[1] for row in selected}

    assert "https://www.databricks.com/blog/ai-gateway-governance-layer-agentic-ai" in selected_urls
    assert "https://www.starburst.io/blog/starburst-integrates-with-google-cloud-lakehouse" not in selected_urls


def test_select_weekly_articles_balances_engine_families():
    candidates = [
        ("Postgres One", "https://example.com/pg1", "PostgreSQL News", 0.95),
        ("Postgres Two", "https://example.com/pg2", "PostgreSQL News", 0.94),
        ("Postgres Three", "https://example.com/pg3", "PostgreSQL News", 0.93),
        ("SQL Server One", "https://example.com/sql1", "SQLServerCentral", 0.92),
        ("MariaDB One", "https://example.com/my1", "MariaDB Foundation", 0.91),
        ("Mongo One", "https://example.com/no1", "MongoDB Blog", 0.90),
        ("Snowflake One", "https://example.com/an1", "Snowflake Blog", 0.89),
        ("Redpanda One", "https://example.com/st1", "Redpanda Blog", 0.88),
        ("General One", "https://example.com/ge1", "DBTA News", 0.87),
    ]

    selected = _select_weekly_articles(candidates, limit=7)
    selected_sources = {row[2] for row in selected}

    assert "SQLServerCentral" in selected_sources
    assert "MariaDB Foundation" in selected_sources
    assert "MongoDB Blog" in selected_sources
    assert "Snowflake Blog" in selected_sources
    assert "Redpanda Blog" in selected_sources
    assert len([row for row in selected if row[2] == "PostgreSQL News"]) <= 2


def test_select_ai_radar_articles_balances_source_families():
    candidates = [
        ("Research One", "https://example.com/r1", "ArXiv ML", 0.95),
        ("Research Two", "https://example.com/r2", "ArXiv CL", 0.94),
        ("Foundation One", "https://example.com/f1", "OpenAI News", 0.93),
        ("Foundation Two", "https://example.com/f2", "Google AI Blog", 0.92),
        ("Vector One", "https://example.com/v1", "Weaviate Blog", 0.91),
        ("Platform One", "https://example.com/p1", "Databricks Engineering Blog", 0.90),
        ("Database One", "https://example.com/d1", "PostgreSQL News", 0.89),
        ("Streaming One", "https://example.com/s1", "Redpanda Blog", 0.88),
    ]

    selected = _select_ai_radar_articles(candidates, limit=7)
    selected_sources = {row[2] for row in selected}

    assert "ArXiv ML" in selected_sources or "ArXiv CL" in selected_sources
    assert "OpenAI News" in selected_sources or "Google AI Blog" in selected_sources
    assert "Weaviate Blog" in selected_sources
    assert "Databricks Engineering Blog" in selected_sources
    assert "PostgreSQL News" in selected_sources


def test_ai_radar_relevance_prefers_data_engineering_ai_topics():
    strong_score = _ai_radar_relevance_score(
        "Databricks Engineering Blog",
        "Improving vector indexing for RAG query latency",
        "https://example.com/vector-rag-indexing",
    )
    weak_score = _ai_radar_relevance_score(
        "Databricks Engineering Blog",
        "Why talent transformation is the missing focus in enterprise AI",
        "https://example.com/talent-transformation",
    )

    assert strong_score > weak_score


def test_select_ai_radar_articles_deprioritizes_generic_enterprise_ai():
    candidates = [
        (
            "Why talent transformation is the missing focus in enterprise AI",
            "https://example.com/talent-transformation",
            "Databricks Engineering Blog",
            0.98,
        ),
        (
            "Improving vector indexing for RAG query latency",
            "https://example.com/vector-rag-indexing",
            "Databricks Engineering Blog",
            0.91,
        ),
        ("Foundation One", "https://example.com/f1", "OpenAI News", 0.93),
        ("Research One", "https://example.com/r1", "ArXiv ML", 0.92),
        ("Vector One", "https://example.com/v1", "Weaviate Blog", 0.90),
    ]

    selected = _select_ai_radar_articles(candidates, limit=4)
    selected_urls = {row[1] for row in selected}

    assert "https://example.com/vector-rag-indexing" in selected_urls
    assert "https://example.com/talent-transformation" not in selected_urls