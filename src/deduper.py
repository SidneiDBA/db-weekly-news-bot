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

from db import get_conn

def dedupe():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE articles_scored
        SET is_duplicate = 1
        WHERE raw_id IN (
            SELECT r1.id
            FROM articles_raw r1
            JOIN articles_raw r2
              ON lower(r1.title) = lower(r2.title)
             AND r1.id > r2.id
        )
    """)

    conn.commit()
    conn.close()