import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

def check_db():
    host = os.getenv("DB_HOST", "192.168.1.27")
    port = int(os.getenv("DB_PORT", "3306"))
    user = os.getenv("DB_USER", "music-management")
    password = os.getenv("DB_PASS", "")
    db_name = os.getenv("DB_DB", "music-management")
    
    conn = pymysql.connect(host=host, port=port, user=user, password=password, db=db_name)
    try:
        with conn.cursor() as cursor:
            print("--- Tabellen ---")
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            for (table,) in tables:
                print(f"\nTabel: {table}")
                cursor.execute(f"DESCRIBE `{table}`")
                columns = cursor.fetchall()
                for col in columns:
                    print(f"  {col[0]} ({col[1]})")
                
                # Toon een paar rijen als het relevant lijkt
                if 'rule' in table.lower() or 'soundcloud' in table.lower() or 'account' in table.lower():
                    print(f"  Data voorbeeld:")
                    cursor.execute(f"SELECT * FROM `{table}` LIMIT 3")
                    rows = cursor.fetchall()
                    for row in rows:
                        print(f"    {row}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_db()
