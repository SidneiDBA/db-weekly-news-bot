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

import subprocess
import json
import time
import os

def call_llm(prompt, use_ollama=None):
    """Call the LLM using ollama if available, otherwise return mock response.
    
    Set use_ollama=False to force mock responses.
    """
    
    # Check if we should try ollama
    if use_ollama is None:
        use_ollama = os.environ.get('USE_OLLAMA', '').lower() == 'true'
    
    if not use_ollama:
        # Return mock response for development/testing
        print("Using mock LLM response (set USE_OLLAMA=true to use actual LLM)")
        return json.dumps({
            "db_engine": "PostgreSQL",
            "topic": "Release",
            "impact_score": 7
        })
    
    # make sure the ollama binary is available before trying to call it
    import shutil
    if shutil.which("ollama") is None:
        print("ollama executable not found on PATH; using mock response")
        return json.dumps({
            "db_engine": "PostgreSQL",
            "topic": "Release",
            "impact_score": 7
        })
    
    # Try to use ollama if enabled
    for attempt in range(2):
        try:
            result = subprocess.run(
                ["ollama", "run", "neural-chat"],
                input=prompt,
                text=True,
                capture_output=True,
                timeout=300
            )
            if result.returncode == 0:
                return result.stdout
            print(f"Ollama error: {result.stderr}")
        except Exception as e:
            # catch any unexpected issue and fall back after a pause
            print(f"Error calling LLM: {e}")
        
        if attempt < 1:
            time.sleep(2)
    
    # Fallback to mock response
    print("Fallback: Using mock LLM response")
    return json.dumps({
        "db_engine": "PostgreSQL",
        "topic": "Release",
        "impact_score": 7
    })
