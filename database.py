# Module Imports
import os
import sys

import mariadb
from dotenv import load_dotenv
from time import sleep


def connect():
    return mariadb.connect(
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
            self.conn = connect()
        except mariadb.Error as e:
            print(f"Error connecting to MariaDB Platform: {e}")
            sleep(10)
            sys.exit(1)

        # Get Cursor
        self.cur = self.conn.cursor()
        self.create_table()

    def create_table(self):
        self.cur.execute('DROP TABLE IF EXISTS song_moods;')
        self.cur.execute('DROP TABLE IF EXISTS songs;')
        self.cur.execute('DROP TABLE IF EXISTS moods;')
        self.cur.execute('DROP TABLE IF EXISTS eps;')
        self.cur.execute('DROP TABLE IF EXISTS labels;')

        self.cur.execute('CREATE TABLE IF NOT EXISTS labels ('
                         ' id integer auto_increment not null unique,'
                         ' name varchar(255) not null unique);')

        self.cur.execute('CREATE TABLE IF NOT EXISTS moods ('
                         ' id integer auto_increment not null unique,'
                         ' name varchar(255) unique);')

        self.cur.execute('CREATE TABLE IF NOT EXISTS genres ('
                         ' id integer auto_increment not null unique,'
                         ' name varchar(255));')

        self.cur.execute('CREATE TABLE IF NOT EXISTS eps ('
                         ' id integer auto_increment not null unique,'
                         ' label_id integer REFERENCES labels(id),'
                         ' catid varchar(255),'
                         ' path varchar(511));')

        self.cur.execute('CREATE TABLE IF NOT EXISTS songs ('
                         ' id integer auto_increment not null unique,'
                         ' label_id integer REFERENCES labels(id),'
                         ' ep_id integer REFERENCES eps(id),'
                         ' filename varchar(511));')

        self.cur.execute('CREATE TABLE IF NOT EXISTS song_moods ('
                         ' id integer auto_increment not null unique,'
                         ' mood_id integer REFERENCES moods(id),'
                         ' song_id integer REFERENCES songs(id));')
        self.conn.commit()

    def insert_label(self, name):
        try:
            query = f"INSERT INTO `labels`(`name`) VALUES (%s)"
            self.cur.execute(query, [name])
        except Exception as e:
            print(e)
            pass

    def clear_eps(self):
        try:
            self.cur.execute('TRUNCATE TABLE `eps`;')
        except Exception as e:
            print(e)
            pass

    def insert_eps(self, label, cat_id, path):
        try:
            query = f"INSERT INTO `eps`(`label_id`, `catid`, `path`) VALUES ((select id from labels where name=%s), %s, %s);"
            self.cur.execute(query, (label, cat_id, path))
        except Exception as e:
            print(e)
            pass

    def insert_mood(self, mood):
        try:
            query = f"INSERT IGNORE INTO  `moods`(`name`) VALUES (%s);"
            self.cur.execute(query, [mood])
        except Exception as e:
            print(query, e)
            pass

    def insert_song(self, filename, label, ep):
        try:
            query = f"INSERT INTO `songs`(`filename`, `label_id`, `ep_id`) VALUES (%s, (select id from labels where name=%s),(select id from eps where path=%s));"
            self.cur.execute(query, (filename, label, ep))
        except Exception as e:
            print(query, e)
            pass

    def insert_song_mood(self, filename, mood):
        try:
            query = f"INSERT INTO `song_moods`(`song_id`, `mood_id`) VALUES ((select id from songs where filename=%s), (select id from moods where name=%s));"
            self.cur.execute(query, (filename, mood))
        except Exception as e:
            print(query, e)
            pass

    def done(self):
        self.conn.commit()

    def start(self):
        # Connect to MariaDB Platform
        try:
            self.conn = connect()
        except mariadb.Error as e:
            print(f"Error connecting to MariaDB Platform: {e}")

        # Get Cursor
        self.cur = self.conn.cursor()
