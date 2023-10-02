# Module Imports
import mariadb
import sys


class Database:
    def __init__(self):
        # Connect to MariaDB Platform
        try:
            conn = mariadb.connect(
                user="music-stats",
                password="stats",
                host="192.0.2.2",
                port=3306,
                database="music-stats"
            )
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

    def insert_label(self, name, eps):
        conn = mariadb.connect(
            user="music-stats",
            password="stats",
            host="192.0.2.2",
            port=3306,
            database="music-stats"
        )
        cur = conn.cursor()
        cur.execute('INSERT INTO `labels`(`name`, `eps`) VALUES (\'' + name + '\',' + eps + ') ON DUPLICATE KEY UPDATE eps='+eps+';;')
        conn.commit()

