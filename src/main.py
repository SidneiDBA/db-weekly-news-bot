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

# Flatten nested source categories
for category in config.get("sources", {}).values():
    if isinstance(category, list):
        for s in category:
            try:
                collect(s["url"], s["name"])
            except Exception as exc:
                print(f"collector error for {s.get('name')}: {exc}")

classify()
dedupe()
generate_weekly()