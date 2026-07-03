import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def check():
    host = os.getenv("DB_HOST", "192.168.1.27")
    port = os.getenv("DB_PORT", "3306")
    user = "root"
    password = "Paced-Splendid-Deuce-Negotiate3-Sappy-Define"
    db_name = os.getenv("DB_DB")
    
    url = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{db_name}"
    engine = create_engine(url)
    
    with engine.connect() as conn:
        query = "SELECT count(*) FROM library_tagged_files t WHERE NOT EXISTS (SELECT 1 FROM library_media_files m WHERE m.file_path_hash = SHA2(t.path, 256))"
        result = conn.execute(text(query)).fetchone()[0]
        print(f"Aantal rijen in library_tagged_files niet in library_media_files: {result}")

if __name__ == "__main__":
    check()
