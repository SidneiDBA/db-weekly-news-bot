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

- Python 3 + `psycopg` PostgreSQL driver
- PostgreSQL (local instance, auto-created database)
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

### 1.5. PostgreSQL (Local)
Ensure PostgreSQL is running locally. If your user cannot auto-create databases, create it manually:
```bash
createdb db_weekly_new
```

### 1.6. Install Python Dependencies
```bash
pip install -r requirements.txt
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
export RSS_HEALTH_CHECK_TIMEOUT=5
python3 src/main.py
```

**First run may take 2-5 minutes** as the model loads into memory.

### Option B: With Mock Responses (Testing/Development)
No LLM dependency needed:

```bash
cd db-weekly-news-bot
export RSS_HEALTH_CHECK_TIMEOUT=5
python3 src/main.py
```

Output will use canned JSON responses instead of the real LLM.

### Option C: AI Radar Mode (LLM + AI/Data Sources)
Generates `output/ai_radar_brief.md` using only the `ai_data` domain sources.

```bash
cd db-weekly-news-bot
export USE_OLLAMA=true
export REPORT_MODE=ai_radar
export RSS_HEALTH_CHECK_TIMEOUT=5
python3 src/main.py
```

One-line alternative:

```bash
REPORT_MODE=ai_radar USE_OLLAMA=true python3 src/main.py
```

Recommended one-liner with RSS pre-check enabled:

```bash
REPORT_MODE=ai_radar USE_OLLAMA=true RSS_HEALTH_CHECK_TIMEOUT=5 python3 src/main.py
```

### Option D: Local `.env` Setup (Copy/Paste)
Create a `.env` file in the project root so you don't need to export variables each run:

```bash
cat > .env << 'EOF'
USE_OLLAMA=true
REPORT_MODE=weekly
RSS_HEALTH_CHECK_TIMEOUT=5

# PostgreSQL settings
PGHOST=localhost
PGPORT=5432
PGUSER=db_weekly_new_user
PGPASSWORD=change_me
PGDATABASE=db_weekly_new
PGMAINTENANCE_DB=postgres
EOF
```

Then run:

```bash
python3 src/main.py
```

---

## 🔧 Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `USE_OLLAMA` | `false` | Set to `true` to use real Ollama LLM; `false` uses mock responses |
| `REPORT_MODE` | `weekly` | `weekly` generates `weekly_brief.md`; `ai_radar` generates `ai_radar_brief.md` |
| `RSS_HEALTH_CHECK_TIMEOUT` | `0` | Seconds to wait for RSS feed response; `0` disables health check (waits indefinitely); set to `3-5` to skip slow/dead feeds |
| `PGHOST` | (unset) | PostgreSQL host; unset uses local socket/peer auth |
| `PGPORT` | (unset) | PostgreSQL port; set when using TCP host |
| `PGUSER` | current OS user | PostgreSQL user |
| `PGPASSWORD` | `` | PostgreSQL password |
| `PGDATABASE` | `db_weekly_new` | Target database (auto-created if missing) |
| `PGMAINTENANCE_DB` | `postgres` | Admin database used to create `PGDATABASE` |

The app also auto-loads these values from a local `.env` file in the project root.

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
│   ├── db.py                          # PostgreSQL connection manager
│   ├── schema.py                      # Database schema
│   └── __pycache__/
├── output/
│   └── weekly_brief.md                # Generated output
├── (no local .db file)               # Data stored in PostgreSQL
├── requirements.txt
├── schema.py
└── README.md
```

---

## 🗄️ Database

The project uses **PostgreSQL** with automatic database and schema initialization.

### Tables
- **articles_raw**: Raw articles from RSS feeds
  - `id`, `source`, `title`, `url`, `published_at`, `content`

- **articles_scored**: Classified and scored articles
  - `id`, `raw_id`, `db_engine`, `topic`, `impact_score`, `is_duplicate`

### Querying the Database

From Python:
```python
import psycopg
from schema import init_db

conn = psycopg.connect(
   host="localhost",
   port=5432,
   user="postgres",
   password="your_password",
   dbname="db_weekly_new",
)
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
- Optionally performs a fast pre-flight RSS health check before full fetch
- Skips feeds that fail to respond within `RSS_HEALTH_CHECK_TIMEOUT`
- Stores raw articles in `articles_raw` table

### 2. **Classifier** (`classifier.py`)
- Uses Ollama LLM to classify each article
- Extracts: `db_engine`, `topic`, and relevance signals used to compute `impact_score` (0.0-1.0)
- Stores in `articles_scored` table

### 3. **Deduper** (`deduper.py`)
- Marks duplicate articles with `is_duplicate = TRUE`
- Prevents redundant content in final brief

### 4. **Article Generator** (`article_generator.py`)
- Queries articles with `impact_score >= 3` and `is_duplicate = FALSE`
- Uses LLM to generate human-readable summaries
- Outputs formatted **weekly_brief.md**

### 5. **URL Health Check** (`url_health.py`)
- Runs automatically after brief generation
- Extracts URLs from the generated Markdown output
- Prints a summary of OK vs broken links in the run output
- Exits the run with non-zero status when broken links are detected (CI-friendly)

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

### Pipeline hangs on slow RSS feeds
**Solution:** Enable RSS pre-check and skip slow/unavailable feeds:
```bash
RSS_HEALTH_CHECK_TIMEOUT=5 python3 src/main.py
```
Use `3-5` seconds in normal environments, or `0` to disable pre-check.

### PostgreSQL authentication error
**Solution:** Check `PGUSER` and `PGPASSWORD`, and verify PostgreSQL is running locally.

### PostgreSQL "database does not exist" error
**Solution:** The app auto-creates `PGDATABASE` from `PGMAINTENANCE_DB`; ensure your role has `CREATEDB` privilege.

### PostgreSQL "table does not exist" error
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
- Database and schema initialization automatic (no manual setup needed)

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

This project is licensed under the **GNU General Public License v3.0**.

- SPDX identifier: `GPL-3.0-or-later`
- Full license text: [LICENSE](LICENSE)
- Optional source-file notice template: [COPYRIGHT_HEADER.txt](COPYRIGHT_HEADER.txt)

---

## 👤 Contributing

Contributions are welcome.

- Fork the repository and create a feature branch.
- Keep changes focused and aligned with the existing project style.
- Run the project locally (`python3 src/main.py`) to validate behavior.
- Open a Pull Request with a clear summary of what changed and why.
- By contributing, you agree your contributions are licensed under `GPL-3.0-or-later`.

---

## 🔗 Resources

- [Ollama Documentation](https://ollama.com/docs)
- [neural-chat Model](https://ollama.com/library/neural-chat)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
