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
import xml.etree.ElementTree as ET
import re
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
        text = text.replace("&nbsp;", " ")
        text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text)
        text = re.sub(
            r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9A-Fa-f]+;)[A-Za-z0-9]+;",
            " ",
            text,
        )
        return ET.fromstring(text)

def collect(feed_url, source_name):
    """Fetch an RSS feed and store articles in the database.
    Uses only stdlib: urllib + xml.etree.ElementTree (no external deps).
    """
    try:
        # Add User-Agent header (many servers block requests without it)
        req = urllib.request.Request(
            feed_url,
            headers={'User-Agent': 'Mozilla/5.0 (compatible; DBWeeklyBot/1.0)'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            feed_xml = response.read()
    except Exception as e:
        print(f"Error fetching {source_name} ({feed_url}): {e}")
        return

    try:
        root = _try_parse_xml(feed_xml)
    except ET.ParseError as e:
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

        original_link = link
        link = _repair_link(link, content)

        if not title or not link:
            continue

        try:
            if link != original_link and original_link:
                cur.execute(
                    """
                    UPDATE articles_raw
                    SET url = ?
                    WHERE source = ? AND title = ? AND url = ?
                    """,
                    (link, source_name, title, original_link),
                )

            cur.execute("""
                INSERT OR IGNORE INTO articles_raw
                (source, title, url, published_at, content)
                VALUES (?, ?, ?, ?, ?)
            """, (source_name, title, link, published, content))
        except Exception as e:
            print(f"DB error for {title}: {e}")

    conn.commit()
    conn.close()