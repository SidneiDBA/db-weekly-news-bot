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