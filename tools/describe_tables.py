
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tools.db_url import database_url

load_dotenv()

def describe():
    engine = create_engine(database_url())
    
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
