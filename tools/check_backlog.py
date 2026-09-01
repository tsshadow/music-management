from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tools.db_url import database_url

load_dotenv()


def check():
    engine = create_engine(database_url())

    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM rules_genre_backlog")).fetchall()
        print(f"Rijen in rules_genre_backlog: {len(result)}")
        for row in result:
            print(row)


if __name__ == "__main__":
    check()
