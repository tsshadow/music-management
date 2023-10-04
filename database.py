# Module Imports
import os
import sys

import mariadb
from dotenv import load_dotenv


def connect():
    return  mariadb.connect(
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASS'),
            host=os.getenv('DB_HOST'),
            port=int(os.getenv('DB_PORT')),
            database=os.getenv('DB_DATABASE')
        )


class Database:

    def __init__(self):
        load_dotenv()
        # Connect to MariaDB Platform
        try:
            conn = connect()
        except mariadb.Error as e:
            print(f"Error connecting to MariaDB Platform: {e}")
            sys.exit(1)

        # Get Cursor
        self.cur = conn.cursor()
        self.create_table()


    def create_table(self):
        self.cur.execute('CREATE TABLE IF NOT EXISTS labels ('
                         ' name varchar(255) not null unique,'
                         ' eps int);')
        self.cur.execute('DROP TABLE eps')
        self.cur.execute('CREATE TABLE IF NOT EXISTS eps ('
                         ' label varchar(255),'
                         ' catid varchar(255),'
                         ' path varchar(255));')

    def insert_label(self, name, eps):
        conn = connect()
        cur = conn.cursor()
        cur.execute('INSERT INTO `labels`(`name`, `eps`) '
                    'VALUES (%s, %s) '
                    'ON DUPLICATE KEY UPDATE eps=%s;',
                    (name, eps, eps))
        conn.commit()

    def clear_eps(self):
        conn = connect()
        cur = conn.cursor()
        cur.execute('TRUNCATE TABLE `eps`;')
        conn.commit()

    def insert_eps(self, label, cat_id, path):
        conn = connect()
        cur = conn.cursor()
        cur.execute('INSERT INTO `eps`(`label`, `catid`, `path`) '
                    'VALUES (%s, %s, %s);',
                    (label, cat_id, path))
        conn.commit()


