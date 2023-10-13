# Module Imports
import os
import sys

import mariadb
from dotenv import load_dotenv


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
            self.cur.execute('INSERT INTO `labels`(`name`) '
                             'VALUES (\'' + name + '\') ')
        except Exception:
            pass

    def clear_eps(self):
        try:
            self.cur.execute('TRUNCATE TABLE `eps`;')
        except Exception:
            pass

    def insert_eps(self, label, cat_id, path):
        try:
            self.cur.execute('INSERT INTO `eps`(`label_id`, `catid`, `path`) '
                             'VALUES ((select id from labels where name=\'' + label + '\'), \'' + cat_id + '\', \'' + path + '\');')
        except Exception:
            pass

    def insert_mood(self, mood):
        try:
            self.cur.execute('INSERT IGNORE INTO  `moods`(`name`) '
                             'VALUES (\'' + mood + '\');')
        except Exception:
            pass

    def insert_song(self, filename, label, ep):
        try:
            self.cur.execute('INSERT INTO `songs`(`filename`, `label_id`, `ep_id`)'
                             'VALUES (\'' + filename + '\', (select id from labels where name=\'' + label + '\'),'
                                                                                                            ' (select id from eps where path=\'' + ep + '\'));')
        except Exception:
            pass

    def insert_song_mood(self, filename, mood):
        try:
            self.cur.execute('INSERT INTO `song_moods`(`song_id`, `mood_id`)'
                             'VALUES ((select id from songs where filename=\'' + filename + '\'), (select id from moods where name=\'' + mood + '\'));')
        except Exception:
            pass

    # def update_label_mood_count(self, label, mood, count):
    #     conn = connect()
    #     cur = conn.cursor()
    #     self.cur.execute('INSERT INTO `label_mood_counts`(`label_id`, `moods_id`, `count`) '
    #                 'VALUES ((select id from labels where name='+name+'), (select id from moods where name='+name+'), '+name+');'
    #                 'ON DUPLICATE KEY UPDATE count='+name+';',
    #                 label, mood, count, count)
    #     conn.commit()
    # def update_ep_mood_count(self, ep_path, mood, count):
    #     conn = connect()
    #     cur = conn.cursor()
    #     self.cur.execute('INSERT INTO `ep_mood_counts`(`ep_id`, `moods_id`, `count`) '
    #                 'VALUES ((select id from eps where path='+name+'), (select id from moods where name='+name+'), '+name+');'
    #                 'ON DUPLICATE KEY UPDATE count='+name+';',
    #                 ep_path, mood, count, count)
    #     conn.commit()
    #
    # def get_ep_mood_count(self, mood):
    #     conn = connect()
    #     cur = conn.cursor()
    #     self.cur.execute('SELECT count  from `ep_mood_counts` where mood=(select id from moods where name='+name+')', mood)
    #     return cur.fetchall()

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
