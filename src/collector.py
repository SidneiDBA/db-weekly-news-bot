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

import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
import re
import os
import gzip
from db import get_conn


def _extract_urls(text):
    if not text:
        return []
    href_urls = re.findall(r'href=["\'](https?://[^"\']+)["\']', text, flags=re.IGNORECASE)
    raw_urls = re.findall(r'https?://[^\s<>")\']+', text)
    seen = set()
    urls = []
    for candidate in href_urls + raw_urls:
        if candidate not in seen:
            seen.add(candidate)
            urls.append(candidate)
    return urls


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


def _repair_link(link, content):
    link = _canonicalize_url(link)
    candidates = _extract_urls(content)
    if not candidates:
        return link

    candidates = [_canonicalize_url(candidate) for candidate in candidates]

    if link in candidates:
        return link

    matching_prefixes = [url for url in candidates if url.startswith(link) and len(url) > len(link)]
    if len(matching_prefixes) == 1:
        return matching_prefixes[0]

    return link

def _try_parse_xml(feed_bytes):
    try:
        return ET.fromstring(feed_bytes)
    except ET.ParseError:
        text = feed_bytes.decode("utf-8", errors="ignore")
        # Some providers prepend junk bytes before the XML declaration.
        first_xml = text.find("<")
        if first_xml > 0:
            text = text[first_xml:]
        text = text.replace("&nbsp;", " ")
        text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text)
        text = re.sub(
            r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9A-Fa-f]+;)[A-Za-z0-9]+;",
            " ",
            text,
        )
        return ET.fromstring(text)


def _candidate_feed_urls(feed_url):
    candidates = []
    parsed = urllib.parse.urlparse(feed_url)
    path = parsed.path.rstrip("/")

    for suffix in ("/feed", "/rss", "/rss.xml", "/feed.xml", "/atom.xml", "/index.xml"):
        if path.endswith(suffix):
            base = path[: -len(suffix)] or "/"
            alternatives = ["/feed", "/feed.xml", "/rss", "/rss.xml", "/atom.xml", "/index.xml"]
            for alt in alternatives:
                new_path = (base.rstrip("/") + alt) if base != "/" else alt
                if new_path != parsed.path:
                    candidates.append(parsed._replace(path=new_path, query="").geturl())

    return list(dict.fromkeys(candidates))


def _extract_alternate_feed_url(html_text, base_url):
    pattern = re.compile(
        r"<link[^>]+rel=[\"'][^\"']*alternate[^\"']*[\"'][^>]*>",
        flags=re.IGNORECASE,
    )
    for match in pattern.findall(html_text):
        link_type = re.search(r"type=[\"']([^\"']+)[\"']", match, flags=re.IGNORECASE)
        href = re.search(r"href=[\"']([^\"']+)[\"']", match, flags=re.IGNORECASE)
        if not href:
            continue
        feed_type = (link_type.group(1).lower() if link_type else "")
        if "rss" in feed_type or "atom" in feed_type or feed_type.endswith("xml"):
            return urllib.parse.urljoin(base_url, href.group(1))
    return None


def _fetch_url_bytes(url, timeout=10):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; DBWeeklyBot/1.0)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html;q=0.8, */*;q=0.5",
            "Accept-Encoding": "gzip",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        payload = response.read()
        content_encoding = response.headers.get("Content-Encoding", "").lower()
        if content_encoding == "gzip" or payload[:2] == b"\x1f\x8b":
            payload = gzip.decompress(payload)
        return payload

def _check_feed_health(feed_url, timeout=5):
    """Quick health check for RSS feed URL.
    
    Returns True if feed responds within timeout, False otherwise.
    Uses a short timeout to avoid blocking on slow/dead feeds.
    """
    try:
        req = urllib.request.Request(
            feed_url,
            headers={'User-Agent': 'Mozilla/5.0 (compatible; DBWeeklyBot/1.0)'}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            # Just check if we can connect and get a response
            return response.status == 200
    except Exception as e:
        print(f"Feed health check failed for {feed_url}: {e}")
        return False

def collect(feed_url, source_name):
    """Fetch an RSS feed and store articles in the database.
    Uses only stdlib: urllib + xml.etree.ElementTree (no external deps).
    
    Skips feeds that fail a quick health check (if enabled).
    """
    # Optional pre-flight health check with short timeout
    health_check_timeout = int(os.environ.get('RSS_HEALTH_CHECK_TIMEOUT', '0'))
    if health_check_timeout > 0:
        if not _check_feed_health(feed_url, timeout=health_check_timeout):
            print(f"Skipping {source_name} - feed did not respond within {health_check_timeout}s")
            return
    tried_urls = [feed_url]
    feed_xml = None
    fetch_errors = []

    for candidate_url in [feed_url] + _candidate_feed_urls(feed_url):
        try:
            feed_xml = _fetch_url_bytes(candidate_url, timeout=10)
            if candidate_url != feed_url:
                print(f"Info: {source_name} feed fallback URL used: {candidate_url}")
            break
        except Exception as e:
            fetch_errors.append((candidate_url, e))
            tried_urls.append(candidate_url)

    if feed_xml is None:
        first_url, first_error = fetch_errors[0] if fetch_errors else (feed_url, "unknown error")
        print(f"Error fetching {source_name} ({first_url}): {first_error}")
        return

    try:
        root = _try_parse_xml(feed_xml)
    except ET.ParseError as e:
        html_text = feed_xml.decode("utf-8", errors="ignore")
        alt_url = _extract_alternate_feed_url(html_text, feed_url)
        if alt_url and alt_url not in tried_urls:
            try:
                alt_xml = _fetch_url_bytes(alt_url, timeout=10)
                root = _try_parse_xml(alt_xml)
                print(f"Info: {source_name} discovered alternate feed URL: {alt_url}")
            except Exception:
                print(f"Error parsing RSS from {source_name}: {e}")
                return
        else:
            print(f"Error parsing RSS from {source_name}: {e}")
            return

    # Handle both RSS 2.0 and Atom namespaces
    items = root.findall(".//item")  # RSS 2.0
    if not items:
        items = root.findall(".//entry", {"ns": "http://www.w3.org/2005/Atom"})  # Atom
    if not items:
        items = root.findall("{http://www.w3.org/2005/Atom}entry")  # Atom with ns

    conn = get_conn()
    cur = conn.cursor()

    for item in items:
        # RSS 2.0
        title_elem = item.find("title")
        link_elem = item.find("link")
        pub_elem = item.find("pubDate")
        desc_elem = item.find("description")

        # Atom fallback
        if title_elem is None:
            title_elem = item.find("{http://www.w3.org/2005/Atom}title")
        if link_elem is None:
            link_elem = item.find("{http://www.w3.org/2005/Atom}link")
            if link_elem is not None:
                link_elem.text = link_elem.get("href", "")
        if pub_elem is None:
            pub_elem = item.find("{http://www.w3.org/2005/Atom}published")
        if desc_elem is None:
            desc_elem = item.find("{http://www.w3.org/2005/Atom}summary")

        title = title_elem.text if title_elem is not None else ""
        link = link_elem.text if link_elem is not None else ""
        published = pub_elem.text if pub_elem is not None else ""
        content = desc_elem.text if desc_elem is not None else ""

        # Resolve relative URLs to absolute using the feed's base URL
        if link and not link.startswith("http"):
            link = urllib.parse.urljoin(feed_url, link)

        original_link = link
        link = _repair_link(link, content)

        if not title or not link:
            continue

        try:
            if link != original_link and original_link:
                cur.execute(
                    """
                    UPDATE articles_raw
                    SET url = %s
                    WHERE source = %s AND title = %s AND url = %s
                    """,
                    (link, source_name, title, original_link),
                )

            cur.execute("""
                INSERT INTO articles_raw
                (source, title, url, published_at, content)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (url) DO NOTHING
            """, (source_name, title, link, published, content))
        except Exception as e:
            print(f"DB error for {title}: {e}")

    conn.commit()
    conn.close()