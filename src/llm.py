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
    
    # Try to use ollama if enabled
    for attempt in range(2):
        try:
            result = subprocess.run(
                ["ollama", "run", "neural-chat"],
                input=prompt,
                text=True,
                capture_output=True,
                timeout=60
            )
            if result.returncode == 0:
                return result.stdout
            print(f"Ollama error: {result.stderr}")
        except Exception as e:
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
