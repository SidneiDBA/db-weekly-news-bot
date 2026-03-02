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

# No external dependencies required - uses only stdlib modules (json, etc.)
from collector import collect
from classifier import classify
from deduper import dedupe
from article_generator import generate_weekly
import json

import os

# determine project root (parent of this script)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# load configuration (sources list)
config_path = os.path.join(ROOT, "config", "sources.json")
try:
    with open(config_path) as f:
        config = json.load(f)
except FileNotFoundError:
    print(f"Error: {config_path} not found")
    config = {}
except json.JSONDecodeError as e:
    print(f"Error parsing {config_path}: {e}")
    config = {}

mode = os.environ.get("REPORT_MODE", "weekly").strip().lower()
domains_to_process = None
if mode == "ai_radar":
    domains_to_process = ["ai_data"]

selected_sources = []

# Support both config formats:
# 1) legacy: {"sources": {"vendors": [...], ...}}
# 2) v2: {"version":"2.0", "domains": {"relational": {"sources": [...]}}}
if isinstance(config.get("domains"), dict):
    for domain_name, domain_cfg in config.get("domains", {}).items():
        if domains_to_process and domain_name not in domains_to_process:
            continue
        for source in domain_cfg.get("sources", []):
            selected_sources.append(source.get("name", ""))
            try:
                collect(source["url"], source["name"])
            except Exception as exc:
                print(f"collector error for {source.get('name')} in {domain_name}: {exc}")
else:
    # legacy fallback
    for category in config.get("sources", {}).values():
        if isinstance(category, list):
            for source in category:
                try:
                    collect(source["url"], source["name"])
                except Exception as exc:
                    print(f"collector error for {source.get('name')}: {exc}")

classify(allowed_sources=selected_sources if selected_sources else None, mode=mode)
dedupe()
generate_weekly(report_mode=mode, allowed_sources=selected_sources if selected_sources else None)