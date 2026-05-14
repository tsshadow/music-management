import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def inspect_db():
    host = os.getenv("DB_HOST", "192.168.1.27")
    port = os.getenv("DB_PORT", "3306")
    user = os.getenv("DB_USER", "music-management")
    password = os.getenv("DB_PASS", "")
    db_name = os.getenv("DB_DB", "music-management")
    
    url = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{db_name}"
    engine = create_engine(url)
    
    with engine.connect() as conn:
        print("Tabellen in de database:")
        result = conn.execute(text("SHOW TABLES"))
        tables = [row[0] for row in result]
        for table in tables:
            count_res = conn.execute(text(f"SELECT COUNT(*) FROM `{table}`"))
            count = count_res.fetchone()[0]
            print(f" - {table}: {count} rijen")

if __name__ == "__main__":
    inspect_db()
