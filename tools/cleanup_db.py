from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tools.db_url import database_url

load_dotenv()


def cleanup():
    engine = create_engine(database_url())

    with engine.connect() as conn:
        # 1. Migreer resterende data
        # print("Migreren van genre_backlog naar rules_genre_backlog...")
        # conn.execute(text("INSERT IGNORE INTO rules_genre_backlog (genre) SELECT genre FROM genre_backlog"))

        # 2. Lijst van oude tabellen om te verwijderen
        old_tables = ["library_tagged_files"]

        print("Uitzetten van foreign key checks...")
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))

        for table in old_tables:
            print(f"Verwijderen van oude tabel: {table}...")
            try:
                conn.execute(text(f"DROP TABLE IF EXISTS `{table}`"))
            except Exception as e:
                print(f"Fout bij verwijderen van {table}: {e}")

        print("Aanzetten van foreign key checks...")
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        conn.commit()
        print("Opschonen voltooid!")


if __name__ == "__main__":
    cleanup()
