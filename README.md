# db-weekly-news-bot
# 🗞️ Database Engineering Weekly News Bot

An automated, no-cost system that collects, classifies, and generates a **weekly technical briefing** for Database Administrators and Database Engineers.

## 🎯 Purpose
Help DBAs stay up to date with **high-impact changes** in:
- PostgreSQL
- SQL Server
- Oracle
- MySQL
- Cloud databases

Focused on **production impact**, not generic tech news.

---

## 🧠 How It Works

1. Collects articles from trusted RSS sources
2. Normalizes and classifies content using an LLM
3. Scores impact on production databases
4. Deduplicates similar news
5. Generates a Weekly Database Engineering Brief in Markdown

---

## 🧱 Architecture

- Python 3 (standard library only – no external package dependencies)
- SQLite (no-cost, auto-initialized)
- LLM via **Ollama** (local, self-hosted)
- GitHub Actions (weekly execution)
- Markdown output

---

## 📋 Prerequisites & Setup

### 1. Python 3.x
Ensure Python 3 is installed:
```bash
python3 --version
```

### 2. Ollama CLI Installation (Required for Real LLM)
Download and install Ollama from [https://ollama.com/download](https://ollama.com/download)

**For Linux:**
```bash
sudo apt-get update && sudo apt-get install -y zstd
curl -fsSL https://ollama.com/download/ollama-linux-amd64.tar.zst | \
  sudo tar --zstd -xvf - -C /usr/local
```

**Verify installation:**
```bash
which ollama
ollama --version
```

### 3. Start Ollama Service
```bash
ollama serve &
```

### 4. Download the Neural-Chat Model
```bash
ollama pull neural-chat
```

**Verify the model is installed:**
```bash
ollama list
```

Expected output:
```
NAME                  ID              SIZE      MODIFIED
neural-chat:latest    89fa737d3b85    4.1 GB    <timestamp>
```

---

## 🚀 Quick Start

### Option A: With Real LLM (Recommended)
Requires Ollama running (see Prerequisites above)

```bash
cd db-weekly-news-bot
export USE_OLLAMA=true
python3 src/main.py
```

**First run may take 2-5 minutes** as the model loads into memory.

### Option B: With Mock Responses (Testing/Development)
No external dependencies needed:

```bash
cd db-weekly-news-bot
python3 src/main.py
```

Output will use canned JSON responses instead of the real LLM.

---

## 🔧 Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `USE_OLLAMA` | `false` | Set to `true` to use real Ollama LLM; `false` uses mock responses |

**Example:**
```bash
USE_OLLAMA=true python3 src/main.py
```

---

## 📁 Project Structure

```
db-weekly-news-bot/
├── .github/
│   └── workflows/
│       └── weekly.yml                 # GitHub Actions schedule
├── config/
│   ├── sources.json                   # News source URLs
│   └── sources.yaml
├── prompts/
│   ├── article_weekly.txt             # Prompt for weekly brief
│   └── classify_weekly.txt            # Prompt for classification
├── src/
│   ├── main.py                        # Entry point
│   ├── collector.py                   # Fetches articles from RSS
│   ├── classifier.py                  # LLM-based classification
│   ├── deduper.py                     # Removes duplicate articles
│   ├── article_generator.py           # Generates Markdown brief
│   ├── llm.py                         # LLM integration (Ollama/mock)
│   ├── db.py                          # SQLite connection manager
│   ├── schema.py                      # Database schema
│   └── __pycache__/
├── output/
│   └── weekly_brief.md                # Generated output
├── db_news.db                         # SQLite database (auto-created)
├── requirements.txt
├── schema.py
└── README.md
```

---

## 🗄️ Database

The project uses **SQLite** with automatic schema initialization.

### Tables
- **articles_raw**: Raw articles from RSS feeds
  - `id`, `source`, `title`, `url`, `published_at`, `content`

- **articles_scored**: Classified and scored articles
  - `id`, `raw_id`, `db_engine`, `topic`, `impact_score`, `is_duplicate`

### Querying the Database

From Python:
```python
import sqlite3
from schema import init_db

conn = sqlite3.connect("db_news.db")
init_db(conn)  # Ensure schema exists
cursor = conn.cursor()

cursor.execute("""
    SELECT r.title, r.url, s.impact_score 
    FROM articles_raw r
    JOIN articles_scored s ON s.raw_id = r.id
    WHERE s.impact_score >= 3
    ORDER BY s.impact_score DESC
    LIMIT 10
""")

for row in cursor.fetchall():
    print(row)

conn.close()
```

---

## 🔄 How the Pipeline Works

### 1. **Collector** (`collector.py`)
- Fetches articles from configured RSS sources
- Stores raw articles in `articles_raw` table

### 2. **Classifier** (`classifier.py`)
- Uses Ollama LLM to classify each article
- Extracts: `db_engine`, `topic`, `impact_score` (1-10)
- Stores in `articles_scored` table

### 3. **Deduper** (`deduper.py`)
- Marks duplicate articles with `is_duplicate = 1`
- Prevents redundant content in final brief

### 4. **Article Generator** (`article_generator.py`)
- Queries articles with `impact_score >= 3` and `is_duplicate = 0`
- Uses LLM to generate human-readable summaries
- Outputs formatted **weekly_brief.md**

---

## ✅ Path Handling

**Important:** All file paths are **absolute** (computed from script location), so the project **works from any working directory**:

```bash
# All of these work identically:
cd /home/user && python3 /path/to/db-weekly-news-bot/src/main.py
cd /home/user/db-weekly-news-bot && python3 src/main.py
python3 /path/to/db-weekly-news-bot/src/main.py
```

The code internally resolves paths relative to the project root using `__file__` and `os.path.dirname()`.

---

## 🐛 Troubleshooting

### "Error: config/sources.json not found"
**Solution:** Ensure all paths are absolute. Run from project root:
```bash
cd db-weekly-news-bot
python3 src/main.py
```

Or use absolute paths (already handled in code).

### "Error calling LLM: No such file or directory: 'ollama'"
**Solution:** Install Ollama and ensure it's on your PATH:
```bash
which ollama
# If not found, install: https://ollama.com/download
```

### "ollama executable not found on PATH; using mock response"
This is **normal** if `USE_OLLAMA=true` but Ollama isn't installed. The script falls back gracefully to mock responses.

### Ollama timeout after 300 seconds
- **First run:** Model loading takes time (2-5 min)
- **Subsequent runs:** Should complete in seconds once loaded
- **Check model status:** `ollama list`

### SQLite "table does not exist" error
**Solution:** The schema is auto-initialized on first run. If you're querying directly, wrap in:
```python
from schema import init_db
init_db(conn)  # Create tables if needed
```

---

## ⏱️ Execution Modes

### Automated (GitHub Actions)
- Runs **weekly** on schedule
- Uses Ollama via `USE_OLLAMA=true` environment variable
- Output committed to `output/weekly_brief.md`

### Manual (Local)
```bash
# Development mode (mock LLM, instant)
python3 src/main.py

# Production mode (real LLM, slower first run)
USE_OLLAMA=true python3 src/main.py
```

---

## 🛠️ Recent Changes & Fixes

### Fixed Issues
1. **Path Resolution** – Changed from relative to absolute paths so scripts work from any directory
   - Updated: `main.py`, `article_generator.py`, `db.py`
   - Now computes project root using `__file__` and `os.path.dirname()`

2. **Ollama Error Handling** – Added graceful fallback to mock responses when Ollama isn't available
   - Added `shutil.which("ollama")` check upfront
   - Prevents repeated error messages in logs

3. **File Not Found Errors** – Fixed relative path issues
   - Replaced hardcoded paths like `"prompts/article_weekly.txt"` with absolute paths
   - All config, prompt, and output paths computed dynamically

4. **LLM Timeout** – Increased timeout from 60s to 300s for first model load
   - Accommodates slower machines and initial model loading

### Configuration Improvements
- Added `USE_OLLAMA` environment variable for easy LLM toggle
- Improved error messages to show full paths
- Graceful degradation when Ollama is unavailable
- Database initialization automatic (no manual setup needed)

---

## 📝 Output Example

Generated **weekly_brief.md**:
```markdown
## 🔥 Top Updates This Week
1. Sql failover cluster issue with different edition setup (enterprise with standard)
   - Summary: [LLM-generated analysis]
   - Link: https://dba.stackexchange.com/...

## 🧠 Trends Observed
- More attention towards interoperability between different SQL Server editions
- Increasing focus on understanding PostgreSQL internals

## 🎯 Why This Matters
- Understanding how different editions interact aids in choosing appropriate solutions
- Performance optimization is essential for successful database management

## 🛠️ Action Items for DBAs
- Read up on failover cluster issues and SQL Server editions
- Monitor PostgreSQL statistics and optimization strategies
```

---

## 📄 License

[Add your license here]

---

## 👤 Contributing

[Add contribution guidelines here]

---

## 🔗 Resources

- [Ollama Documentation](https://ollama.com/docs)
- [neural-chat Model](https://ollama.com/library/neural-chat)
- [SQLite Documentation](https://www.sqlite.org/docs.html)
