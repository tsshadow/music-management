
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tools.db_url import database_url

load_dotenv()

def finalize():
    engine = create_engine(database_url())
    
    with engine.connect() as conn:
        print("Migreren van data uit rules_genres naar rules_genres_new...")
        # Voeg ontbrekende genres toe
        conn.execute(text("""
            INSERT IGNORE INTO rules_genres_new (name, corrected_genre)
            SELECT genre, corrected_genre FROM rules_genres
        """))
        
        # Check counts
        count_old = conn.execute(text("SELECT count(*) FROM rules_genres")).fetchone()[0]
        count_new = conn.execute(text("SELECT count(*) FROM rules_genres_new")).fetchone()[0]
        print(f"Oude tabel: {count_old} rijen, Nieuwe tabel: {count_new} rijen")
        
        print("Hernoemen van tabellen...")
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        conn.execute(text("RENAME TABLE rules_genres TO rules_genres_old"))
        conn.execute(text("RENAME TABLE rules_genres_new TO rules_genres"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        
        conn.commit()
        print("Genre migratie voltooid!")

if __name__ == "__main__":
    finalize()
