import sys
import unittest
from unittest.mock import MagicMock

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.mp3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())

import services.music_manager.routers.users

services.music_manager.routers.users.run_lms_db_sync = lambda: None
import services.music_manager.database

services.music_manager.database.get_db_connection = MagicMock(return_value=None)

from services.music_manager.routers import news


class NewsSchemaTest(unittest.TestCase):

    def test_creates_both_tables_and_seeds_the_nos_source(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        news.init_db(cursor)
        statements = ' '.join(call[0][0] for call in cursor.execute.call_args_list)
        self.assertIn('CREATE TABLE IF NOT EXISTS news_sources', statements)
        self.assertIn('CREATE TABLE IF NOT EXISTS news_bulletins', statements)
        self.assertIn('INSERT IGNORE INTO news_sources', statements)
        seeded = [call[0][1] for call in cursor.execute.call_args_list if len(call[0]) > 1]
        self.assertIn(news.DEFAULT_STREAM_URL, seeded[0])
