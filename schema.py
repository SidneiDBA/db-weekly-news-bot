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

def init_db(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS articles_raw (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            title TEXT,
            url TEXT UNIQUE,
            published_at TEXT,
            content TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS articles_scored (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_id INTEGER,
            db_engine TEXT,
            topic TEXT,
            impact_score REAL,
            is_duplicate INTEGER DEFAULT 0
        )
    """)
    conn.commit()