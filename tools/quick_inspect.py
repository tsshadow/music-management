"""Print every table of the music-management database with its row count.

Connection settings come from the environment: DB_HOST, DB_USER and DB_PASS are required,
DB_PORT (3306) and DB_NAME (music-management) are optional. A `.env` file is read too.
"""

import os
import sys

import pymysql
from dotenv import load_dotenv

REQUIRED_VARS = ("DB_HOST", "DB_USER", "DB_PASS")


def connection_settings_from_env(env=None):
    """Return host, port, user, password and database read from the environment.

    Exits with a message that names every missing required variable.
    """
    env = os.environ if env is None else env
    missing = [name for name in REQUIRED_VARS if not env.get(name)]
    if missing:
        sys.exit(f"Missing environment variable(s): {', '.join(missing)}. Set them or put them in .env.")
    return {
        "host": env["DB_HOST"],
        "port": int(env.get("DB_PORT") or 3306),
        "user": env["DB_USER"],
        "password": env["DB_PASS"],
        "database": env.get("DB_NAME") or "music-management",
    }


def inspect():
    """Connect with the environment settings and print table row counts and rating samples."""
    settings = connection_settings_from_env()
    host = settings["host"]
    port = settings["port"]
    user = settings["user"]
    password = settings["password"]
    db_name = settings["database"]

    print(f"Connecting to {host}:{port}/{db_name} as {user}...")

    try:
        conn = pymysql.connect(host=host, port=port, user=user, password=password, database=db_name)
    except Exception as e:
        sys.exit(f"Connection to {host}:{port}/{db_name} failed: {e}")

    try:
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            tables = [row[0] for row in cursor.fetchall()]
            print("\nTables and row counts:")
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
                count = cursor.fetchone()[0]
                print(f" - {table}: {count} rows")

            # Specifically check for rating tables
            for t in ["track_ratings", "rating_tracks"]:
                if t in tables:
                    print(f"\nSample data from {t}:")
                    cursor.execute(f"SELECT * FROM `{t}` LIMIT 5")
                    rows = cursor.fetchall()
                    for r in rows:
                        print(f"   {r}")
                else:
                    print(f"\nTable '{t}' does not exist.")
    finally:
        conn.close()


if __name__ == "__main__":
    load_dotenv()
    inspect()
