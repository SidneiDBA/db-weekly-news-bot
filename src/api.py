from fastapi import FastAPI
from pathlib import Path
import os
import sys

# Add src directory to path so imports work
sys.path.insert(0, os.path.dirname(__file__))

from article_generator import generate_weekly

# determine project root (parent of this script)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# load configuration (sources list)
config_path = os.path.join(ROOT, "src", "article_generator.py")
app = FastAPI(title="DB Weekly News API")

@app.get("/weekly")
def get_weekly():
    # regenerate the weekly brief before serving
    # Only regenerate when a real LLM is enabled; mock responses will
    # otherwise overwrite the brief with JSON (see article_generator validation)
    if os.environ.get("USE_OLLAMA", "").lower() == "true":
        try:
            generate_weekly()
        except Exception as e:
            # log and continue; previous brief may still exist
            print(f"error generating weekly brief: {e}")
    else:
        print("skipping generation: USE_OLLAMA not set to true")

    content = Path("output/weekly_brief.md").read_text()
    return {
        "format": "markdown",
        "content": content
    }