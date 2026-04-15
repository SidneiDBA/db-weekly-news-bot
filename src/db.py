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

import os
from functools import lru_cache
import getpass
from pathlib import Path

try:
    import psycopg
    from psycopg import sql
except ModuleNotFoundError as exc:
    psycopg = None
    sql = None
    _psycopg_import_error = exc
else:
    _psycopg_import_error = None
from schema import init_db


@lru_cache(maxsize=1)
def _load_env_file():
    root = Path(__file__).resolve().parents[1]
    env_file = root / ".env"
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@lru_cache(maxsize=1)
def _db_settings():
    _load_env_file()
    return {
        "host": os.environ.get("PGHOST"),
        "port": int(os.environ.get("PGPORT", "5432")) if os.environ.get("PGPORT") else None,
        "user": os.environ.get("PGUSER", getpass.getuser()),
        "password": os.environ.get("PGPASSWORD"),
        "database": os.environ.get("PGDATABASE", "db_weekly_new"),
        "maintenance_db": os.environ.get("PGMAINTENANCE_DB", "postgres"),
    }


def _connect(dbname):
    if psycopg is None:
        raise RuntimeError(
            "Missing dependency 'psycopg'. Install requirements and run with the project venv, "
            "for example: /home/srinc/.venv/bin/python src/main.py"
        ) from _psycopg_import_error

    settings = _db_settings()
    conn_kwargs = {
        "dbname": dbname,
        "user": settings["user"],
    }
    if settings["host"]:
        conn_kwargs["host"] = settings["host"]
    if settings["port"]:
        conn_kwargs["port"] = settings["port"]
    if settings["password"]:
        conn_kwargs["password"] = settings["password"]
    return psycopg.connect(**conn_kwargs)


@lru_cache(maxsize=1)
def _ensure_database_exists():
    if sql is None:
        raise RuntimeError(
            "Missing dependency 'psycopg'. Install requirements and run with the project venv, "
            "for example: /home/srinc/.venv/bin/python src/main.py"
        ) from _psycopg_import_error

    settings = _db_settings()
    target_db = settings["database"]

    with _connect(settings["maintenance_db"]) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
            if cur.fetchone() is None:
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_db)))


def get_conn():
    _ensure_database_exists()
    conn = _connect(_db_settings()["database"])
    init_db(conn)
    return conn