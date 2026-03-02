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

import os, sqlite3
from schema import init_db

import os, sqlite3

here = os.path.dirname(__file__)                     # …/src
db_path = os.path.join(here, "..", "db_news.db")     # ../db_news.db
db_path = os.path.abspath(db_path)

conn = sqlite3.connect(db_path)
init_db(conn)  # Initialize the database schema
cursor = conn.cursor()

# Execute a query
cursor.execute("""
        SELECT r.title, r.url
        FROM articles_raw r
        JOIN articles_scored s ON s.raw_id = r.id
        WHERE s.impact_score >= 3
          AND s.is_duplicate = 0
        ORDER BY s.impact_score DESC
        LIMIT 7
    """)  # Replace 'articles' with your table name
results = cursor.fetchall()

print(f"{len(results)} rows returned")
for row in results:
    print(row)

conn.close()