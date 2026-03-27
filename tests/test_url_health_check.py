import sys
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from url_health import _check_url


def test_url_health_treats_403_as_reachable():
    http_403 = HTTPError(
        url="https://openai.com/index/introducing-text-and-code-embeddings",
        code=403,
        msg="Forbidden",
        hdrs=None,
        fp=None,
    )

    with patch("urllib.request.urlopen", side_effect=http_403):
        is_ok, status, _ = _check_url("https://openai.com/index/introducing-text-and-code-embeddings")

    assert is_ok is True
    assert status == 403


def test_url_health_keeps_404_as_broken():
    http_404 = HTTPError(
        url="https://example.com/missing-page",
        code=404,
        msg="Not Found",
        hdrs=None,
        fp=None,
    )

    with patch("urllib.request.urlopen", side_effect=http_404):
        is_ok, status, _ = _check_url("https://example.com/missing-page")

    assert is_ok is False
    assert status == 404
