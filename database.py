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
        self.cur.execute('DROP TABLE IF EXISTS song_moods;')
        self.cur.execute('DROP TABLE IF EXISTS songs;')

        self.cur.execute('DROP TABLE IF EXISTS moods;')
        self.cur.execute('DROP TABLE IF EXISTS eps;')
        # self.cur.execute('DROP TABLE IF EXISTS label_mood_counts;')
        self.cur.execute('DROP TABLE IF EXISTS labels;')

        self.cur.execute('CREATE TABLE IF NOT EXISTS labels ('
                         ' id integer auto_increment not null unique,'
                         ' name varchar(255) not null unique);')

        self.cur.execute('CREATE TABLE IF NOT EXISTS moods ('
                         ' id integer auto_increment not null unique,'
                         ' name varchar(255));')

        self.cur.execute('CREATE TABLE IF NOT EXISTS genres ('
                         ' id integer auto_increment not null unique,'
                         ' name varchar(255));')

        self.cur.execute('CREATE TABLE IF NOT EXISTS eps ('
                         ' id integer auto_increment not null unique,'
                         ' label_id integer REFERENCES labels(id),'
                         ' catid varchar(255),'
                         ' path varchar(511));')

        # self.cur.execute('CREATE TABLE IF NOT EXISTS label_mood_counts ('
        #                  ' id integer auto_increment not null unique,'
        #                  ' label_id integer REFERENCES labels(id),'
        #                  ' mood_id integer REFERENCES moods(id),'
        #                  ' count integer);')
        #
        # self.cur.execute('CREATE TABLE IF NOT EXISTS ep_mood_counts ('
        #                  ' id integer auto_increment not null unique,'
        #                  ' ep_id integer REFERENCES eps(id),'
        #                  ' mood_id integer REFERENCES moods(id),'
        #                  ' count integer);')

        self.cur.execute('CREATE TABLE IF NOT EXISTS songs ('
                         ' id integer auto_increment not null unique,'
                         ' label_id integer REFERENCES labels(id),'
                         ' ep_id integer REFERENCES eps(id),'
                         ' filename varchar(511));')

        self.cur.execute('CREATE TABLE IF NOT EXISTS song_moods ('
                         ' id integer auto_increment not null unique,'
                         ' mood_id integer REFERENCES moods(id),'
                         ' song_id integer REFERENCES songs(id));')

    def insert_label(self, name):
        conn = connect()
        cur = conn.cursor()
        cur.execute('INSERT INTO `labels`(`name`) '
                    'VALUES (%s) ',
                    name)
        conn.commit()

    def clear_eps(self):
        conn = connect()
        cur = conn.cursor()
        cur.execute('TRUNCATE TABLE `eps`;')
        conn.commit()

    def insert_eps(self, label, cat_id, path):
        conn = connect()
        cur = conn.cursor()
        cur.execute('INSERT INTO `eps`(`label_id`, `catid`, `path`) '
                    'VALUES ((select id from labels where name=%s), %s, %s);',
                    (label, cat_id, path))
        conn.commit()

    def insert_mood(self, mood):
        conn = connect()
        cur = conn.cursor()
        cur.execute('INSERT IGNORE  INTO `moods`(`mood`) '
                    'VALUES (%s);',
                    mood)
        conn.commit()

    def insert_song(self, filename, label, ep):
        conn = connect()
        cur = conn.cursor()
        cur.execute('INSERT IGNORE  INTO `songs`(`filename`, `label_id`, `catid`)'
                    'VALUES (%s, (select id from labels where name=%s), %s);',
                    filename, label, ep)
        conn.commit()

    def insert_song_mood(self, filename, mood):
        conn = connect()
        cur = conn.cursor()
        cur.execute('INSERT IGNORE  INTO `song_moods`(`song_id`, `mood_id`, `catid`)'
                    'VALUES ((select id from songs where filename=%s), (select id from moods where mood=%s), %s);',
                    filename, mood)
        conn.commit()

    # def update_label_mood_count(self, label, mood, count):
    #     conn = connect()
    #     cur = conn.cursor()
    #     cur.execute('INSERT INTO `label_mood_counts`(`label_id`, `moods_id`, `count`) '
    #                 'VALUES ((select id from labels where name=%s), (select id from moods where name=%s), %s);'
    #                 'ON DUPLICATE KEY UPDATE count=%s;',
    #                 label, mood, count, count)
    #     conn.commit()
    # def update_ep_mood_count(self, ep_path, mood, count):
    #     conn = connect()
    #     cur = conn.cursor()
    #     cur.execute('INSERT INTO `ep_mood_counts`(`ep_id`, `moods_id`, `count`) '
    #                 'VALUES ((select id from eps where path=%s), (select id from moods where name=%s), %s);'
    #                 'ON DUPLICATE KEY UPDATE count=%s;',
    #                 ep_path, mood, count, count)
    #     conn.commit()
    #
    # def get_ep_mood_count(self, mood):
    #     conn = connect()
    #     cur = conn.cursor()
    #     cur.execute('SELECT count  from `ep_mood_counts` where mood=(select id from moods where name=%s)', mood)
    #     return cur.fetchall()


