import os
import subprocess
import pymysql
import sqlite3
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    try:
        host = os.getenv('DB_HOST', 'localhost')
        port = int(os.getenv('DB_PORT', '3306'))
        
        # Handle host:port format
        if ':' in host and not host.startswith('['):
            host, port_str = host.split(':', 1)
            port = int(port_str)

        conn = pymysql.connect(
            host=host, 
            port=port, 
            user=os.getenv('DB_USER', 'music-management'), 
            password=os.getenv('DB_PASS', ''), 
            db=os.getenv('DB_DB', 'music-management'), 
            cursorclass=pymysql.cursors.DictCursor
        )
        return conn
    except Exception as e:
        print(f'❌ MariaDB Connection error: {e}')
        return None

def fetch_lms_users_local(db_path):
    print(f"📖 Reading local LMS database: {db_path}")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT id, login_name, listenbrainz_token FROM user')
        users = []
        for row in cursor.fetchall():
            users.append({'lms_id': row[0], 'username': row[1], 'lb_token': row[2] or ''})
        conn.close()
        return users
    except Exception as e:
        print(f'❌ Error reading local LMS DB: {e}')
        return []

def fetch_lms_users_ssh():
    remote_host = os.getenv('REMOTE_HOST', '192.0.2.27')
    remote_user = os.getenv('REMOTE_USER', 'root')
    remote_pass = os.getenv('REMOTE_PASS', 'queue')
    db_path = os.getenv('REMOTE_LMS_DB_PATH', '/docker/lms/var/lms/lms.db')
    
    print(f"🌐 Fetching users from remote LMS via SSH: {remote_user}@{remote_host}:{db_path}")
    
    query = 'SELECT id, login_name, listenbrainz_token FROM user;'
    # Use sshpass if available, otherwise regular ssh
    ssh_prefix = f"sshpass -p {remote_pass} " if remote_pass else ""
    cmd = f"""{ssh_prefix}ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 {remote_user}@{remote_host} 'sqlite3 {db_path} "{query}"'"""
    
    try:
        result = subprocess.check_output(cmd, shell=True).decode('utf-8')
        users = []
        for line in result.strip().split('\n'):
            if line:
                parts = line.split('|')
                if len(parts) >= 2:
                    users.append({
                        'lms_id': parts[0], 
                        'username': parts[1], 
                        'lb_token': parts[2] if len(parts) > 2 else ''
                    })
        return users
    except Exception as e:
        print(f'❌ Error fetching LMS users via SSH: {e}')
        print("Tip: Zorg dat sshpass is geïnstalleerd of gebruik sleutel-gebaseerde authenticatie.")
        return []

def main():
    db_path = os.getenv('LMS_DB_PATH')
    
    if db_path and os.path.exists(db_path):
        lms_users = fetch_lms_users_local(db_path)
    else:
        lms_users = fetch_lms_users_ssh()

    if not lms_users:
        print('❌ Geen gebruikers gevonden of er is een fout opgetreden.')
        return

    print(f'✅ {len(lms_users)} gebruikers gevonden in LMS.')
    
    conn = get_db_connection()
    if not conn:
        return

    try:
        with conn.cursor() as cursor:
            for user in lms_users:
                print(f"🔄 Verwerken: {user['username']} (LMS ID: {user['lms_id']})")
                
                # Update of insert gebruiker
                cursor.execute('''
                    INSERT INTO users (username, display_name, lms_user_id)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE lms_user_id = VALUES(lms_user_id), display_name = VALUES(display_name)
                ''', (user['username'], user['username'], user['lms_id']))
                
                # Zoek interne ID voor ListenBrainz koppeling
                cursor.execute('SELECT id FROM users WHERE username = %s', (user['username'],))
                internal_user = cursor.fetchone()
                
                if internal_user and user['lb_token']:
                    user_id = internal_user['id']
                    print(f"  ✨ ListenBrainz token toegevoegd voor {user['username']}")
                    cursor.execute('''
                        INSERT INTO user_listenbrainz_accounts (user_id, lb_username, lb_token)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE lb_token = VALUES(lb_token), lb_username = VALUES(lb_username)
                    ''', (user_id, user['username'], user['lb_token']))
            
            conn.commit()
            print('\n🎉 Synchronisatie succesvol voltooid!')
    except Exception as e:
        print(f'❌ Fout tijdens database updates: {e}')
    finally:
        conn.close()

if __name__ == '__main__':
    main()