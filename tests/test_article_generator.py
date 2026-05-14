import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from article_generator import _remove_unknown_urls


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