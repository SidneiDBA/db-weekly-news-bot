import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from article_generator import _normalize_report_template, _remove_unknown_urls


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