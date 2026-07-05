import os
import pymysql
from dotenv import load_dotenv

# Laad .env bestand vanuit de project root
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)

def get_db_connection():
    # Probeer host van .env te gebruiken, val terug naar localhost als we buiten docker draaien
    host = os.getenv("DB_HOST", "localhost")
    if host == "db":
        host = "localhost"
    
    # Als we op de remote server draaien, is het waarschijnlijk ook localhost voor dit script
    # tenzij we specifiek naar de remote host wijzen.
    
    try:
        conn = pymysql.connect(
            host=host,
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "music-management"),
            password=os.getenv("DB_PASS", ""),
            database=os.getenv("DB_DB", "music-management"),
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=5
        )
        return conn
    except Exception as e:
        # Probeer 192.168.1.27 als backup (vanuit inspect_db.py)
        if host == "localhost":
            try:
                conn = pymysql.connect(
                    host="192.168.1.27",
                    port=int(os.getenv("DB_PORT", "3306")),
                    user=os.getenv("DB_USER", "music-management"),
                    password=os.getenv("DB_PASS", ""),
                    database=os.getenv("DB_DB", "music-management"),
                    cursorclass=pymysql.cursors.DictCursor,
                    connect_timeout=2
                )
                return conn
            except:
                pass
        
        print(f"\x1b[31mFout: Kon geen verbinding maken met de database op {host}.\x1b[0m")
        print("Zorg ervoor dat de database container draait of dat de SSH tunnel actief is.")
        return None

def print_stats():
    conn = get_db_connection()
    if not conn:
        return

    print("\n\x1b[1;36m=== MuMaFi Library Statistieken ===\x1b[0m")
    try:
        with conn.cursor() as cursor:
            # 1. Algemene tellingen
            cursor.execute("SELECT COUNT(*) as count FROM library_tracks")
            total_tracks = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM library_artists")
            total_artists = cursor.fetchone()['count']
            
            print(f"\x1b[1mTracks:\x1b[0m   {total_tracks}")
            print(f"\x1b[1mArtiesten:\x1b[0m {total_artists}")
            
            cursor.execute("SHOW TABLES LIKE 'library_albums'")
            if cursor.fetchone():
                cursor.execute("SELECT COUNT(*) as count FROM library_albums")
                print(f"\x1b[1mAlbums:\x1b[0m    {cursor.fetchone()['count']}")

            # 2. Top Artiesten
            print("\n\x1b[1;33mTop 5 Artiesten (meeste tracks):\x1b[0m")
            cursor.execute("""
                SELECT a.name, COUNT(t.id) as track_count 
                FROM library_artists a
                JOIN library_tracks t ON a.id = t.primary_artist_id
                GROUP BY a.id
                ORDER BY track_count DESC
                LIMIT 5
            """)
            for i, row in enumerate(cursor.fetchall(), 1):
                print(f" {i}. {row['name']} \x1b[90m({row['track_count']} tracks)\x1b[0m")

            # 3. Match rate & Scrobbles
            cursor.execute("SHOW TABLES LIKE 'scrobble_listens'")
            if cursor.fetchone():
                cursor.execute("SELECT COUNT(*) as count FROM scrobble_listens")
                scrobbles = cursor.fetchone()['count']
                
                cursor.execute("SHOW TABLES LIKE 'scrobble_unmatched_listens'")
                if cursor.fetchone():
                    cursor.execute("SELECT COUNT(*) as count FROM scrobble_unmatched_listens")
                    unmatched = cursor.fetchone()['count']
                    total = scrobbles + unmatched
                    if total > 0:
                        rate = round((scrobbles / total) * 100, 2)
                        color = "\x1b[32m" if rate > 80 else "\x1b[33m"
                        print(f"\n\x1b[1mListenBrainz Match Rate:\x1b[0m {color}{rate}%\x1b[0m ({scrobbles}/{total})")

            # 4. Recent toegevoegd
            print("\n\x1b[1;32mRecent toegevoegd:\x1b[0m")
            cursor.execute("""
                SELECT t.title, a.name as artist
                FROM library_tracks t
                JOIN library_artists a ON t.primary_artist_id = a.id
                ORDER BY t.created_at DESC
                LIMIT 3
            """)
            for row in cursor.fetchall():
                print(f" - {row['artist']} - {row['title']}")

    except Exception as e:
        print(f"\x1b[31mFout bij ophalen statistieken: {e}\x1b[0m")
    finally:
        conn.close()
    print("\x1b[1;36m====================================\x1b[0m\n")

if __name__ == "__main__":
    print_stats()
