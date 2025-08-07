import os
import sys
import time
import types
import unittest
import importlib

from fastapi.testclient import TestClient

# Minimal env vars for Settings
os.environ.setdefault('import_folder_path', '/tmp')
os.environ.setdefault('music_folder_path', '/tmp')
os.environ.setdefault('eps_folder_path', '/tmp')
os.environ.setdefault('delimiter', '/')
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_USER', 'user')
os.environ.setdefault('DB_PORT', '0')
os.environ.setdefault('DB_PASS', '')
os.environ.setdefault('DB_DB', 'db')


class ServerEndpointsTest(unittest.TestCase):
    def setUp(self):
        self.original_modules = {}

        def _make_stub_module(module_name, class_names):
            mod = types.ModuleType(module_name)
            for cls in class_names:
                if cls == 'Tagger':
                    class StubTagger:
                        def run(self, *a, **k):
                            pass

                        @staticmethod
                        def available_tags():
                            return []

                        @staticmethod
                        def parse_song(*a, **k):
                            pass

                    setattr(mod, cls, StubTagger)
                else:
                    setattr(
                        mod,
                        cls,
                        type(cls, (), {
                            '__init__': lambda self, *a, **k: None,
                            'run': lambda self, *a, **k: None,
                        }),
                    )
            return mod

        modules_to_stub = {
            'downloader.youtube': ['YoutubeDownloader'],
            'downloader.soundcloud': ['SoundcloudDownloader'],
            'downloader.telegram': ['TelegramDownloader'],
            'processing.converter': ['Converter'],
            'processing.epsflattener': ['EpsFlattener'],
            'processing.extractor': ['Extractor'],
            'processing.mover': ['Mover'],
            'processing.renamer': ['Renamer'],
            'postprocessing.repair': ['FileRepair'],
            'postprocessing.sanitizer': ['Sanitizer'],
            'postprocessing.tagger': ['Tagger'],
            'postprocessing.analyze': ['Analyze'],
            'postprocessing.artistfixer': ['ArtistFixer'],
        }

        for mod_name in set(m.split('.')[0] for m in modules_to_stub):
            if mod_name not in sys.modules:
                self.original_modules[mod_name] = None
                sys.modules[mod_name] = types.ModuleType(mod_name)

        for full_name, classes in modules_to_stub.items():
            self.original_modules[full_name] = sys.modules.get(full_name)
            sys.modules[full_name] = _make_stub_module(full_name, classes)

        # provide minimal main module exposing Step
        from step import Step as RealStep
        self.original_modules['main'] = sys.modules.get('main')
        main_mod = types.ModuleType('main')
        main_mod.Step = RealStep
        sys.modules['main'] = main_mod

        import api.server as server_module
        self.server = importlib.reload(server_module)
        self.Step = RealStep
        self.client = TestClient(self.server.app)
        self.server.jobs.clear()

    def tearDown(self):
        for name, mod in self.original_modules.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod

    def test_steps_and_jobs_listing(self):
        resp = self.client.get('/api/steps')
        self.assertEqual(resp.status_code, 200)
        steps = resp.json()['steps']
        self.assertIn('tag', steps)
        self.assertIn('import', steps)

        # simulate a running job and verify listing
        job_id = '123'
        self.server.jobs[job_id] = {'id': job_id, 'step': 'dummy', 'status': 'running', 'log': []}
        jobs_resp = self.client.get('/api/jobs')
        self.assertEqual(jobs_resp.status_code, 200)
        jobs = jobs_resp.json()['jobs']
        self.assertTrue(any(job['id'] == job_id and job['step'] == 'dummy' for job in jobs))


if __name__ == '__main__':
    unittest.main()
