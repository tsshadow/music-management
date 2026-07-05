import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

def cleanup_genres():
    conn = pymysql.connect(
        host="192.168.1.27",
        port=3306,
        user="music-management",
        password="Properly-Urologist9-Onlooker-Stupor-Triage-Rocket",
        db="music-management"
    )
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SHOW INDEX FROM rules_genres")
            indices = cursor.fetchall()
            
            to_drop = []
            for idx in indices:
                key_name = idx[2]
                if key_name.startswith("name_") or (key_name == "name" and to_drop):
                    # We want to keep ONLY one 'name' index.
                    # Actually, let's keep the one called 'name' if it exists, and drop others.
                    if key_name == "name":
                        continue
                    to_drop.append(key_name)
            
            # If 'name' doesn't exist but name_X does, we should keep one.
            has_name = any(idx[2] == "name" for idx in indices)
            if not has_name and to_drop:
                keep = to_drop.pop(0)
                print(f"Keeping {keep} as the primary unique index (renaming to 'name' later)")
            
            for key in to_drop:
                print(f"Dropping index {key}...")
                try:
                    cursor.execute(f"ALTER TABLE rules_genres DROP INDEX {key}")
                except Exception as e:
                    print(f"Failed to drop {key}: {e}")
            
            conn.commit()
            print("Cleanup finished.")
    finally:
        conn.close()

if __name__ == "__main__":
    cleanup_genres()
