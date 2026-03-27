"""Tests for RSS feed health check functionality."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from collector import _check_feed_health


def test_health_check_returns_true_for_successful_response():
    """Health check should return True when feed responds with 200."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.__enter__ = lambda self: self
    mock_response.__exit__ = lambda self, *args: None
    
    with patch('urllib.request.urlopen', return_value=mock_response):
        assert _check_feed_health('https://example.com/feed.xml') is True


def test_health_check_returns_false_on_timeout():
    """Health check should return False when feed times out."""
    with patch('urllib.request.urlopen', side_effect=TimeoutError("timeout")):
        assert _check_feed_health('https://slow-feed.example.com/feed.xml', timeout=1) is False


def test_health_check_returns_false_on_connection_error():
    """Health check should return False on network errors."""
    with patch('urllib.request.urlopen', side_effect=ConnectionError("unreachable")):
        assert _check_feed_health('https://dead-feed.example.com/feed.xml') is False


def test_health_check_uses_correct_timeout():
    """Health check should pass timeout parameter to urlopen."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.__enter__ = lambda self: self
    mock_response.__exit__ = lambda self, *args: None
    
    with patch('urllib.request.urlopen', return_value=mock_response) as mock_urlopen:
        _check_feed_health('https://example.com/feed.xml', timeout=3)
        # Verify timeout was passed
        assert mock_urlopen.call_args[1]['timeout'] == 3
