
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tools.db_url import database_url

load_dotenv()

def check():
    engine = create_engine(database_url())
    
    with engine.connect() as conn:
        query = "SELECT count(*) FROM library_tagged_files t WHERE NOT EXISTS (SELECT 1 FROM library_media_files m WHERE m.file_path_hash = SHA2(t.path, 256))"
        result = conn.execute(text(query)).fetchone()[0]
        print(f"Aantal rijen in library_tagged_files niet in library_media_files: {result}")

if __name__ == "__main__":
    check()
