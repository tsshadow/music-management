import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def init_db():
    host = os.getenv("DB_HOST", "192.168.1.27")
    port = os.getenv("DB_PORT", "3306")
    user = os.getenv("DB_USER", "music-management")
    password = os.getenv("DB_PASS", "")
    db_name = os.getenv("DB_DB", "music-management")
    
    url = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{db_name}"
    engine = create_engine(url)
    
    sql_file = "services/ml-analyzer/db_init.sql"
    with open(sql_file, "r") as f:
        sql = f.read()
    
    # Split SQL into individual statements
    statements = sql.split(";")
    
    with engine.connect() as conn:
        for statement in statements:
            if statement.strip():
                print(f"Executing: {statement[:50]}...")
                conn.execute(text(statement))
        conn.commit()
    print("Database succesvol geïnitialiseerd!")

if __name__ == "__main__":
    init_db()
