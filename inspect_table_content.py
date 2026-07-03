import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def inspect_table(table_name, limit=5):
    host = os.getenv("DB_HOST", "192.168.1.27")
    port = os.getenv("DB_PORT", "3306")
    user = os.getenv("DB_USER", "music-management")
    password = os.getenv("DB_PASS", "")
    db_name = os.getenv("DB_DB", "music-management")
    
    url = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{db_name}"
    engine = create_engine(url)
    
    with engine.connect() as conn:
        print(f"--- Top {limit} entries from {table_name} ---")
        result = conn.execute(text(f"SELECT * FROM `{table_name}` LIMIT {limit}"))
        keys = result.keys()
        for row in result:
            print(dict(zip(keys, row)))

if __name__ == "__main__":
    import sys
    table = sys.argv[1] if len(sys.argv) > 1 else "downloads_soundcloud_archive"
    inspect_table(table)
