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

import re
import urllib.request
from urllib.error import HTTPError, URLError


def _extract_urls(markdown_text):
    urls = re.findall(r"https?://[^\s)]+", markdown_text)
    deduped = []
    seen = set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
    return deduped


def _check_url(url, timeout=10):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; DBWeeklyBot/1.0)"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return True, response.status, ""
    except HTTPError as exc:
        return False, exc.code, str(exc)
    except URLError as exc:
        return False, None, str(exc)
    except Exception as exc:
        return False, None, str(exc)


def run_url_health_check(markdown_path):
    """Validate URLs in generated markdown and print a concise health summary.

    Returns True when all URLs are healthy (or no URLs found), False otherwise.
    """
    try:
        with open(markdown_path, "r", encoding="utf-8") as f:
            markdown_text = f.read()
    except FileNotFoundError:
        print(f"URL health-check: file not found: {markdown_path}")
        return False

    urls = _extract_urls(markdown_text)
    if not urls:
        print("URL health-check: no URLs found in output")
        return True

    broken = []
    ok_count = 0

    for url in urls:
        is_ok, status, error_message = _check_url(url)
        if is_ok:
            ok_count += 1
        else:
            broken.append((url, status, error_message))

    print(f"URL health-check: {ok_count}/{len(urls)} URLs OK")
    if broken:
        print("URL health-check: broken links detected")
        for url, status, error in broken:
            if status is not None:
                print(f" - [{status}] {url}")
            else:
                print(f" - [ERROR] {url} ({error})")
        return False
    else:
        print("URL health-check: no broken links detected")
        return True
