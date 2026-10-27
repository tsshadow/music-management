"""Drop the duplicate `name_*` unique indices on `rules_genres`.

Connection settings come from the environment: DB_HOST, DB_USER and DB_PASS are required,
DB_PORT (3306) and DB_NAME (music-management) are optional. A `.env` file is read too.
"""

import os
import sys

import pymysql
from dotenv import load_dotenv

REQUIRED_VARS = ("DB_HOST", "DB_USER", "DB_PASS")


def connection_settings_from_env(env=None):
    """Return the `pymysql.connect` keyword arguments read from the environment.

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


def cleanup_genres():
    """Drop every redundant `name_*` index on `rules_genres`, keeping one unique index."""
    conn = pymysql.connect(**connection_settings_from_env())
    try:
        with conn.cursor() as cursor:
            cursor.execute("SHOW INDEX FROM rules_genres")
            indices = cursor.fetchall()
            to_drop = []
            for idx in indices:
                key_name = idx[2]
                if key_name.startswith("name_") or (key_name == "name" and to_drop):
                    if key_name == "name":
                        continue
                    to_drop.append(key_name)
            has_name = any(idx[2] == "name" for idx in indices)
            if not has_name and to_drop:
                keep = to_drop.pop(0)
                print(f"Keeping {keep} as the primary unique index (renaming to 'name' later)")
            for key in to_drop:
                print(f"Dropping index {key}...")
                try:
                    cursor.execute(f"ALTER TABLE rules_genres DROP INDEX {key}")
                except Exception as e:
                    print(f"Failed to drop {key}: {e}")
            conn.commit()
            print("Cleanup finished.")
    finally:
        conn.close()


if __name__ == "__main__":
    load_dotenv()
    cleanup_genres()
