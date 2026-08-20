"""The switch that keeps the background loops out of a test database.

The tagger, scanner and radio loops write on their own schedule. That is right in
production and wrong against the integration database, where the radio scheduler
held radio_timeline rows while the fixtures were emptying every table between
tests and the two waited on each other's locks.
"""
import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())
import services.music_manager.routers.users

services.music_manager.routers.users.run_lms_db_sync = lambda: None
import services.music_manager.database

services.music_manager.database.get_db_connection = MagicMock(return_value=None)

from services.music_manager import main


class BackgroundWorkersEnabledTest(unittest.TestCase):

    def test_workers_run_by_default(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertTrue(main.background_workers_enabled())

    def test_workers_stay_down_when_disabled(self):
        for value in ('1', 'true', 'TRUE', 'yes', ' 1 '):
            with patch.dict('os.environ', {'MUMA_DISABLE_BACKGROUND_WORKERS': value}, clear=True):
                self.assertFalse(main.background_workers_enabled(), value)

    def test_any_other_value_leaves_them_running(self):
        with patch.dict('os.environ', {'MUMA_DISABLE_BACKGROUND_WORKERS': '0'}, clear=True):
            self.assertTrue(main.background_workers_enabled())

    def test_startup_starts_no_thread_when_disabled(self):
        # The long-running loops go through the thread registry so /health can see them, the
        # one-shot tasks are plain Threads; the switch has to hold both back.
        with patch.dict('os.environ', {'MUMA_DISABLE_BACKGROUND_WORKERS': '1'}, clear=True), \
                patch.object(main, 'start_thread') as start_thread, \
                patch.object(main.threading, 'Thread') as thread:
            main.startup_event()
        thread.assert_not_called()
        start_thread.assert_not_called()

    def test_startup_starts_the_loops_when_enabled(self):
        with patch.dict('os.environ', {}, clear=True), \
                patch.object(main, 'start_thread') as start_thread, \
                patch.object(main.threading, 'Thread') as thread:
            main.startup_event()
        self.assertTrue(thread.called)
        registered = {call.args[0] for call in start_thread.call_args_list}
        self.assertEqual({'tagger', 'scanner', 'radio', 'news', 'events-retention'}, registered)
