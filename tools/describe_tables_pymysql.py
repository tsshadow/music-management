import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

def describe_table(table_name):
    host = os.getenv("DB_HOST", "db")
    port = int(os.getenv("DB_PORT", "3306"))
    user = os.getenv("DB_USER", "music-management")
    password = os.getenv("DB_PASS", "")
    db_name = os.getenv("DB_DB", "music-management")
    
    conn = pymysql.connect(host=host, port=port, user=user, password=password, database=db_name)
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"DESCRIBE {table_name}")
            for row in cursor.fetchall():
                print(row)
    finally:
        conn.close()

if __name__ == "__main__":
    describe_table("downloads_youtube_accounts")
    print("-" * 20)
    describe_table("downloads_soundcloud_accounts")
