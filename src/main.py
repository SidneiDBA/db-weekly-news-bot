from collector import collect
from classifier import classify
from deduper import dedupe
from article_generator import generate_weekly
import yaml

sources = yaml.safe_load(open("config/sources.yaml"))

for s in sources:
    collect(s["url"], s["name"])

classify()
dedupe()
generate_weekly()