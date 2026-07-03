import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def describe():
    host = os.getenv("DB_HOST", "192.168.1.27")
    port = os.getenv("DB_PORT", "3306")
    user = "root"
    password = "Paced-Splendid-Deuce-Negotiate3-Sappy-Define"
    db_name = os.getenv("DB_DB")
    
    url = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{db_name}"
    engine = create_engine(url)
    
    tables = [
        "library_tracks",
        "library_media_files",
        "library_track_audio_features",
        "library_track_ml_labels"
    ]
    
    with engine.connect() as conn:
        for table in tables:
            print(f"\n--- {table} ---")
            try:
                result = conn.execute(text(f"DESCRIBE `{table}`"))
                for row in result:
                    print(row)
            except Exception as e:
                print(f"Error: {e}")

if __name__ == "__main__":
    describe()
