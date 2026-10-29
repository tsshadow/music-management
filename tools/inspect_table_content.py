import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tools.env_required import require_env

load_dotenv()


def inspect_table(table_name, limit=5):
    required = require_env("DB_HOST", "DB_USER", "DB_PASS")
    host = required["DB_HOST"]
    port = os.getenv("DB_PORT", "3306")
    user = required["DB_USER"]
    password = required["DB_PASS"]
    db_name = os.getenv("DB_DB", "music-management")

    url = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{db_name}"
    engine = create_engine(url)

    with engine.connect() as conn:
        print(f"--- Top {limit} entries from {table_name} ---")
        result = conn.execute(text(f"SELECT * FROM `{table_name}` LIMIT {limit}"))
        keys = result.keys()
        for row in result:
            print(dict(zip(keys, row, strict=True)))


if __name__ == "__main__":
    import sys

    table = sys.argv[1] if len(sys.argv) > 1 else "downloads_soundcloud_archive"
    inspect_table(table)
