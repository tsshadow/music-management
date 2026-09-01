import argparse
import getpass
import os
import sys

import bcrypt

# Add the project root to sys.path so we can import services
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from services.music_manager.database import get_db_connection
from services.music_manager.routers.users import notify_server_sync_users


def set_password(username, password):
    conn = get_db_connection()
    if not conn:
        print("Error: Could not connect to the database.")
        return False

    try:
        with conn.cursor() as cursor:
            # Check if user exists
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
            if not user:
                print(f"Error: User '{username}' not found.")
                return False

            # Hash password
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            # Update password
            cursor.execute("UPDATE users SET password_hash = %s WHERE username = %s", (password_hash, username))
            conn.commit()
            print(f"Password for user '{username}' has been updated successfully.")

            # Notify server to sync users
            try:
                notify_server_sync_users()
            except Exception as e:
                print(f"Warning: Failed to notify server for sync: {e}")

            return True
    except Exception as e:
        print(f"Error: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set the password for a Music Management user.")
    parser.add_argument("username", nargs="?", help="The username of the user.")
    parser.add_argument("--password", help="The new password (optional, will prompt if not provided).")

    args = parser.parse_args()

    username = args.username
    if not username:
        username = input("Enter username: ")

    password = args.password
    if not password:
        password = getpass.getpass(f"Enter new password for {username}: ")
        confirm_password = getpass.getpass("Confirm new password: ")
        if password != confirm_password:
            print("Error: Passwords do not match.")
            sys.exit(1)

    if set_password(username, password):
        sys.exit(0)
    else:
        sys.exit(1)
