import os
import json
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def backup_db():
    host = os.getenv("DB_HOST", "192.168.1.27")
    port = os.getenv("DB_PORT", "3306")
    user = os.getenv("DB_USER", "music-management")
    password = os.getenv("DB_PASS", "")
    db_name = os.getenv("DB_DB", "music-management")
    
    url = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{db_name}"
    engine = create_engine(url)
    
    backup_data = {}
    
    with engine.connect() as conn:
        print("Backup starten...")
        result = conn.execute(text("SHOW TABLES"))
        tables = [row[0] for row in result]
        
        for table in tables:
            print(f"Dumping {table}...")
            # We halen de data op
            data_res = conn.execute(text(f"SELECT * FROM `{table}`"))
            columns = data_res.keys()
            rows = [dict(zip(columns, row)) for row in data_res]
            
            # We halen ook de CREATE TABLE statement op
            create_res = conn.execute(text(f"SHOW CREATE TABLE `{table}`"))
            create_sql = create_res.fetchone()[1]
            
            backup_data[table] = {
                "create_sql": create_sql,
                "data": rows
            }
            
    with open("backup_before_domain_rename.json", "w") as f:
        # We gebruiken een custom encoder voor datetimes etc indien nodig
        # Maar voor nu proberen we standaard json
        try:
            json.dump(backup_data, f, default=str, indent=2)
            print("Backup opgeslagen in backup_before_domain_rename.json")
        except Exception as e:
            print(f"Fout bij opslaan backup: {e}")

if __name__ == "__main__":
    backup_db()
