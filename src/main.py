from collector import collect
from classifier import classify
from deduper import dedupe
from article_generator import generate_weekly
import yaml

config = yaml.safe_load(open("config/sources.yaml"))

# Flatten nested source categories
for category in config.get("sources", {}).values():
    if isinstance(category, list):
        for s in category:
            collect(s["url"], s["name"])

classify()
dedupe()
generate_weekly()