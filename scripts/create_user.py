import os
import sys
import bcrypt
import secrets
from dotenv import load_dotenv

# Zorg dat we de services kunnen importeren vanaf de root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.music_manager.database import get_db_connection

def create_user(username, password, display_name=None, is_admin=False):
    load_dotenv()
    conn = get_db_connection()
    if not conn:
        print("Error: Kan geen verbinding maken met de MariaDB database.")
        return False
    
    try:
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        api_key = secrets.token_hex(16)
        
        with conn.cursor() as cursor:
            # Check that the table exists (init_db is normally done by the app)
            cursor.execute("SHOW TABLES LIKE 'users'")
            if not cursor.fetchone():
                print("Error: De 'users' tabel bestaat nog niet. Start de music-manager service eerst op om de DB te initialiseren.")
                return False

            cursor.execute('''
                INSERT INTO users (username, display_name, is_admin, password_hash, api_key)
                VALUES (%s, %s, %s, %s, %s)
            ''', (username, display_name or username, is_admin, password_hash, api_key))
            conn.commit()
            print(f"✅ Gebruiker '{username}' succesvol aangemaakt!")
            print(f"🔑 API Key: {api_key}")
            print(f"🛡️ Admin: {'Ja' if is_admin else 'Nee'}")
            return True
    except Exception as e:
        if "Duplicate entry" in str(e):
            print(f"❌ Error: Gebruiker '{username}' bestaat al.")
        else:
            print(f"❌ Error bij aanmaken gebruiker: {e}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Snel een gebruiker aanmaken voor Music Management System.")
        print("\nGebruik:")
        print("  python scripts/create_user.py <gebruikersnaam> <wachtwoord> [weergavenaam] [is_admin: 0|1]")
        print("\nVoorbeeld:")
        print("  python scripts/create_user.py user geheim 'Teun' 1")
        sys.exit(1)
    
    u = sys.argv[1]
    p = sys.argv[2]
    d = sys.argv[3] if len(sys.argv) > 3 else None
    a = sys.argv[4] == '1' if len(sys.argv) > 4 else False
    
    create_user(u, p, d, a)
