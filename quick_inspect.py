import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

def inspect():
    host = "192.168.1.27"
    port = 3306
    user = "music-management"
    password = "Properly-Urologist9-Onlooker-Stupor-Triage-Rocket"
    db_name = "music-management"
    
    print(f"Connecting to {host}:{port}/{db_name} as {user}...")
    
    try:
        conn = pymysql.connect(host=host, port=port, user=user, password=password, database=db_name)
    except Exception as e:
        print(f"Connection failed: {e}")
        # Try local host if default fails
        try:
            print("Retrying with localhost...")
            conn = pymysql.connect(host="localhost", port=port, user=user, password=password, database=db_name)
        except Exception as e2:
            print(f"Connection failed again: {e2}")
            return

    try:
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            tables = [row[0] for row in cursor.fetchall()]
            print("\nTables and row counts:")
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
                count = cursor.fetchone()[0]
                print(f" - {table}: {count} rows")
                
            # Specifically check for rating tables
            for t in ["track_ratings", "rating_tracks"]:
                if t in tables:
                    print(f"\nSample data from {t}:")
                    cursor.execute(f"SELECT * FROM `{t}` LIMIT 5")
                    rows = cursor.fetchall()
                    for r in rows:
                        print(f"   {r}")
                else:
                    print(f"\nTable '{t}' does not exist.")
    finally:
        conn.close()

if __name__ == "__main__":
    inspect()
