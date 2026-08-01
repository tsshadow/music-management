import unittest
from unittest.mock import MagicMock, patch

from services.importer import importer_service
from services.importer.importer_service import ImporterService, parse_args


class ParseArgsTest(unittest.TestCase):

    def test_the_defaults_run_the_pipeline_once(self):
        with patch('sys.argv', ['importer']):
            args = parse_args()
        self.assertFalse(args.repeat)
        self.assertEqual(args.sleeptime, 300)

    def test_the_repeat_and_sleeptime_flags_are_read(self):
        with patch('sys.argv', ['importer', '--repeat', '--sleeptime', '30']):
            args = parse_args()
        self.assertTrue(args.repeat)
        self.assertEqual(args.sleeptime, 30)


class ImporterServiceTest(unittest.TestCase):

    def setUp(self):
        self.settings = MagicMock(dryrun=False)
        patches = [
            patch.object(importer_service, 'Settings', return_value=self.settings),
            patch.object(importer_service, 'Extractor'),
            patch.object(importer_service, 'Renamer'),
            patch.object(importer_service, 'Mover'),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_the_pipeline_is_extract_then_rename_then_move(self):
        service = ImporterService()
        self.assertEqual([step.name for step in service.steps], ['Extractor', 'Renamer', 'Mover'])

    def test_running_the_pipeline_runs_every_step_in_order(self):
        service = ImporterService()
        service.steps = [MagicMock(name='one'), MagicMock(name='two')]
        service.run_import()
        for step in service.steps:
            step.run.assert_called_once_with(service.steps, dry_run=False)

    def test_the_dry_run_setting_is_handed_to_every_step(self):
        self.settings.dryrun = True
        service = ImporterService()
        service.steps = [MagicMock()]
        service.run_import()
        service.steps[0].run.assert_called_once_with(service.steps, dry_run=True)

    def test_a_settings_object_without_a_dryrun_flag_defaults_to_a_real_run(self):
        del self.settings.dryrun
        self.assertFalse(ImporterService().dry_run)


class MainTest(unittest.TestCase):

    def setUp(self):
        self.service = MagicMock()
        patcher = patch.object(importer_service, 'ImporterService', return_value=self.service)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_without_the_repeat_flag_the_pipeline_runs_exactly_once(self):
        with patch('sys.argv', ['importer']), patch.object(importer_service, 'sleep') as sleep:
            importer_service.main()
        self.service.run_import.assert_called_once()
        sleep.assert_not_called()

    def test_with_the_repeat_flag_the_pipeline_sleeps_between_runs(self):
        with patch('sys.argv', ['importer', '--repeat', '--sleeptime', '7']), \
             patch.object(importer_service, 'sleep', side_effect=[None, KeyboardInterrupt]) as sleep:
            with self.assertRaises(KeyboardInterrupt):
                importer_service.main()
        self.assertEqual(sleep.call_args.args, (7,))
        self.assertEqual(self.service.run_import.call_count, 2)

    def test_an_interrupt_during_a_run_ends_the_loop_cleanly(self):
        self.service.run_import.side_effect = KeyboardInterrupt
        with patch('sys.argv', ['importer', '--repeat']), patch.object(importer_service, 'sleep') as sleep:
            importer_service.main()
        sleep.assert_not_called()

    def test_a_failing_run_is_logged_and_the_loop_continues(self):
        self.service.run_import.side_effect = [RuntimeError('boom'), None]
        with patch('sys.argv', ['importer', '--repeat']), \
             patch.object(importer_service, 'sleep', side_effect=[KeyboardInterrupt]):
            with self.assertRaises(KeyboardInterrupt):
                importer_service.main()
        self.assertEqual(self.service.run_import.call_count, 1)


if __name__ == '__main__':
    unittest.main()
