import os
import subprocess
import pymysql
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    try:
        conn = pymysql.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "music-management"),
            password=os.getenv("DB_PASS", ""),
            db=os.getenv("DB_DB", "music-management"),
            cursorclass=pymysql.cursors.DictCursor
        )
        return conn
    except Exception as e:
        print(f"MariaDB Connection error: {e}")
        return None

def fetch_lms_users():
    remote_host = os.getenv("REMOTE_HOST", "192.168.1.27")
    remote_user = os.getenv("REMOTE_USER", "root")
    remote_pass = os.getenv("REMOTE_PASS", "queue")
    db_path = "/docker/lms/var/lms/lms.db"
    
    # Query to get id, login_name, and listenbrainz_token
    query = "SELECT id, login_name, listenbrainz_token FROM user;"
    
    cmd = f"sshpass -p {remote_pass} ssh -o StrictHostKeyChecking=no {remote_user}@{remote_host} 'sqlite3 {db_path} \"{query}\"'"
    
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
                        'lb_token': parts[2] if len(parts) > 2 else ""
                    })
        return users
    except Exception as e:
        print(f"Error fetching LMS users via SSH: {e}")
        return []

def main():
    print("Fetching users from LMS...")
    lms_users = fetch_lms_users()
    if not lms_users:
        print("No users found or error occurred.")
        return

    print(f"Found {len(lms_users)} users in LMS.")
    
    conn = get_db_connection()
    if not conn:
        return

    try:
        with conn.cursor() as cursor:
            for user in lms_users:
                print(f"Processing user: {user['username']} (LMS ID: {user['lms_id']})")
                
                # Insert or update user
                cursor.execute("""
                    INSERT INTO users (username, display_name, lms_user_id)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE lms_user_id = VALUES(lms_user_id), display_name = VALUES(display_name)
                """, (user['username'], user['username'], user['lms_id']))
                
                # Get the internal user_id
                cursor.execute("SELECT id FROM users WHERE username = %s", (user['username'],))
                internal_user = cursor.fetchone()
                
                if internal_user and user['lb_token']:
                    user_id = internal_user['id']
                    # Use a default lb_username for now or empty, as LMS doesn't seem to store it separately in the user table 
                    # (it might be in another table or just assumed same as login_name)
                    lb_username = user['username'] 
                    
                    print(f"  Adding ListenBrainz token for {user['username']}")
                    cursor.execute("""
                        INSERT INTO user_listenbrainz_accounts (user_id, lb_username, lb_token)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE lb_token = VALUES(lb_token), lb_username = VALUES(lb_username)
                    """, (user_id, lb_username, user['lb_token']))
            
            conn.commit()
            print("Migration completed successfully.")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
