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
        result = conn.execute(text("SELECT * FROM rules_genre_backlog")).fetchall()
        print(f"Rijen in rules_genre_backlog: {len(result)}")
        for row in result:
            print(row)

if __name__ == "__main__":
    check()
