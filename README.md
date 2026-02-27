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
- SQLite (no-cost)
- LLM via Ollama (local) or free-tier APIs (requires [\"ollama\" CLI](https://ollama.com/) on the PATH)
- GitHub Actions (weekly execution)
- Markdown output

---

## ⏱️ Execution

Runs automatically **once per week** using GitHub Actions.

Manual execution (requires Python 3, nothing else to install):

```bash
cd db-weekly-news-bot
python3 src/main.py
```

That's it – no `pip install` needed. The project uses only Python standard library modules.

├── .github/
│   └── workflows/
│       └── weekly.yml
├── config/
│   └── sources.yaml
├── prompts/
│   ├── classify_weekly.txt
│   └── weekly_article.txt
├── src/
│   ├── collector.py
│   ├── normalizer.py
│   ├── classifier.py
│   ├── deduper.py
│   ├── article_generator.py
│   ├── llm.py
│   ├── db.py
│   └── main.py
├── output/
│   └── weekly_brief.md
├── db_news.db        # gerado automaticamente
├── requirements.txt
└── README.md