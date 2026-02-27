import urllib.request
import xml.etree.ElementTree as ET
import re
from db import get_conn

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

        if not title or not link:
            continue

        try:
            cur.execute("""
                INSERT OR IGNORE INTO articles_raw
                (source, title, url, published_at, content)
                VALUES (?, ?, ?, ?, ?)
            """, (source_name, title, link, published, content))
        except Exception as e:
            print(f"DB error for {title}: {e}")

    conn.commit()
    conn.close()