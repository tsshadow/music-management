"""The downloader's error paths against the real yt-dlp, in a subprocess.

`services/tests/mock_base.py` replaces `yt_dlp` with a bare module for every test
under `services/`, so the tests there can only assume how yt-dlp reacts to an
error -- and one of them assumed wrong for years: it had `download()` raise on a
403, which yt-dlp never does under ``ignoreerrors``. It reports the error to its
logger and returns normally. What is proved here is exactly that behaviour and
what the downloader now does with it:

* a 403 reported that way parks the YouTube source (the logger is the only
  place the signal appears);
* ``ShuttingDown`` raised from a progress hook ends the whole ``download()``
  call, where a plain exception only abandoned one entry and yt-dlp carried on
  with the next.

A child interpreter has a clean `sys.modules`, for the same reason
`test_artwork_embedding.py` uses one. No network is touched: the extractors are
registered here, and the one download is a ``file://`` URL.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _importable(module: str) -> bool:
    """Whether the interpreter running this suite can import `module` on its own."""
    probe = subprocess.run([sys.executable, '-c', f'import {module}'], capture_output=True, check=False)  # noqa: S603
    return probe.returncode == 0


# Everything else the children import is stubbed (see `use_service_stubs`); yt-dlp
# is the one thing that has to be real. scripts/test/music-management-unit.sh puts
# it on PYTHONPATH when the interpreter lacks it; if even that failed, say so
# plainly rather than fail on an import.
pytestmark = pytest.mark.skipif(
    not _importable('yt_dlp'), reason='the real yt_dlp is not installed for this interpreter'
)

PRELUDE = """
import logging
import os
import sys
import tempfile

sys.path.insert(0, {root!r})

import yt_dlp
from yt_dlp import YoutubeDL
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import DownloadCancelled, ExtractorError

WORK = tempfile.mkdtemp()


class FakeChannelIE(InfoExtractor):
    # Claims the channel URL `download_account` builds; lists two videos.
    IE_NAME = 'fakechannel'
    _VALID_URL = r'https?://www\\.youtube\\.com/(?P<id>@[^/?#]+)$'

    def _real_extract(self, url):
        channel = self._match_id(url)
        return self.playlist_result(
            [self.url_result(f'fakevideo:{{n}}', FakeVideoIE.ie_key(), f'v{{n}}') for n in (1, 2)],
            channel,
            channel,
        )


class FakeVideoIE(InfoExtractor):
    # Every video answers the way YouTube answers a refused client.
    IE_NAME = 'fakevideo'
    _VALID_URL = r'fakevideo:(?P<id>\\d+)$'
    attempted = []

    def _real_extract(self, url):
        video_id = self._match_id(url)
        FakeVideoIE.attempted.append(video_id)
        raise ExtractorError(
            'Unable to download webpage: HTTP Error 403: Forbidden (caused by <HTTPError 403: Forbidden>)',
            video_id=video_id,
            expected=True,
        )


def use_service_stubs(settings):
    # The unit suite's stubs for the database, the settings and the tagger's
    # caches -- everything except yt_dlp, which is the point of this file. Nothing
    # here may reach a database, and the interpreter running it need not have the
    # MariaDB driver or the tagger's dependencies.
    real = {{name: module for name, module in sys.modules.items() if name == 'yt_dlp' or name.startswith('yt_dlp.')}}
    import services.tests.mock_base  # noqa: F401 - installs the stubs on import
    sys.modules.update(real)
    config = sys.modules['services.common.config_store']
    config.ConfigStore.return_value.get_many.side_effect = lambda keys: {{k: settings.get(k) for k in keys}}


def cookie_file():
    # An empty Netscape cookie file, so yt-dlp does not go looking for Firefox.
    path = os.path.join(WORK, 'cookies.txt')
    with open(path, 'w') as handle:
        handle.write('# Netscape HTTP Cookie File\\n')
    return path


def isolated(opts):
    # A YoutubeDL that knows only the extractors registered here.
    ydl = YoutubeDL({{'allowed_extractors': ['-all'], 'quiet': True, **opts}})
    ydl.add_info_extractor(FakeChannelIE())
    ydl.add_info_extractor(FakeVideoIE())
    return ydl
"""


def run_with_real_ytdlp(body: str) -> str:
    """Run `body` in a child interpreter with the real yt-dlp, returning its stdout."""
    script = textwrap.dedent(PRELUDE).format(root=str(ROOT)) + textwrap.dedent(body)
    result = subprocess.run(  # noqa: S603 - a fixed interpreter and a literal script
        [sys.executable, '-c', script],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=ROOT,
    )
    assert result.returncode == 0, f'child failed:\n{result.stdout}\n{result.stderr}'
    return result.stdout.strip().splitlines()[-1]


def test_yt_dlp_under_ignoreerrors_reports_a_403_and_returns_normally():
    """The premise: nothing raises, so an `except` around `download()` never sees the 403."""
    output = run_with_real_ytdlp(
        """
        heard = []

        class Logger:
            def debug(self, msg): pass
            def info(self, msg): pass
            def warning(self, msg): heard.append(msg)
            def error(self, msg): heard.append(msg)

        with isolated({'ignoreerrors': True, 'logger': Logger()}) as ydl:
            ydl.download(['https://www.youtube.com/@blocked'])
        assert FakeVideoIE.attempted == ['1', '2'], FakeVideoIE.attempted
        assert any('HTTP Error 403: Forbidden' in line for line in heard), heard
        print('ok')
        """
    )
    assert output == 'ok'


def test_a_403_reported_to_the_logger_parks_the_youtube_source():
    output = run_with_real_ytdlp(
        """
        use_service_stubs({
            'youtube_folder': os.path.join(WORK, 'youtube'),
            'youtube_archive': os.path.join(WORK, 'archive'),
            'yt_cookies': cookie_file(),
        })
        from services.downloader.account_schedule import AccountSchedule, InMemoryCheckStore
        from services.downloader.rate_state import InMemoryRateStateStore, RateLimited, RateState
        from services.downloader.timing import load_timing
        from services.downloader.write_offs import InMemoryWriteOffStore, WriteOffs
        from services.downloader.youtube import youtube as youtube_module
        from services.downloader.youtube.YoutubeAccount import AUDIO, YoutubeAccount

        assert youtube_module.YoutubeDL is YoutubeDL, 'the stub replaced the real yt-dlp'
        youtube_module.YoutubeArchive.exists = staticmethod(lambda *a, **k: False)

        class Notifier:
            def notify(self, message, title=''):
                return True

        class Downloader(youtube_module.YoutubeDownloader):
            def _create_ydl(self, ydl_opts, download_type=AUDIO):
                # The real YoutubeDL and the real post-processor chain; only the
                # extractors are ours, and the pacing is taken out.
                opts = {k: v for k, v in ydl_opts.items() if not k.startswith(('sleep', 'max_sleep', 'ratelimit'))}
                ydl = super()._create_ydl({**opts, 'allowed_extractors': ['-all']}, download_type)
                ydl.add_info_extractor(FakeChannelIE())
                ydl.add_info_extractor(FakeVideoIE())
                return ydl

        timing = load_timing('youtube', overrides={'deep_sweep_days': 0})
        rate_state = RateState('youtube', timing, store=InMemoryRateStateStore(), jitter=lambda: 1.0)
        downloader = Downloader(
            timing=timing,
            rate_state=rate_state,
            schedule=AccountSchedule('youtube', store=InMemoryCheckStore()),
            write_offs=WriteOffs('youtube', store=InMemoryWriteOffStore(), retry_days=30),
            notifier=Notifier(),
        )
        account = YoutubeAccount(name='@blocked', download_type=AUDIO)

        records = []
        handler = logging.Handler()
        handler.emit = records.append
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

        try:
            downloader.download_account(account, downloader._prepare_ydl_opts(account, None, False))
        except RateLimited as exc:
            parked = exc
        else:
            raise AssertionError('a 403 did not park the source')

        assert parked.reason == '403', parked.reason
        assert rate_state.cooldown_remaining() > 0
        assert downloader.policy.stop.is_set()
        # No retry: the first attempt's report was enough.
        assert FakeVideoIE.attempted == ['1', '2'], FakeVideoIE.attempted
        # And the error went through `logging`, which is what feeds the event log.
        assert any(
            r.levelno == logging.ERROR and 'HTTP Error 403: Forbidden' in r.getMessage() for r in records
        ), [r.getMessage() for r in records]
        print('ok')
        """
    )
    assert output == 'ok'


def test_a_refused_flat_listing_raises_instead_of_reading_as_an_empty_account():
    """The deep sweep's premise: under the caller's ``ignoreerrors`` a 403 listed nothing."""
    output = run_with_real_ytdlp(
        """
        use_service_stubs({})
        from services.downloader.deep_sweep import ListingFailed, list_flat

        class RefusedChannelIE(InfoExtractor):
            IE_NAME = 'refusedchannel'
            _VALID_URL = r'refused:(?P<id>.+)$'

            def _real_extract(self, url):
                raise ExtractorError('Unable to download JSON metadata: HTTP Error 403: Forbidden', expected=True)

        def factory(opts):
            ydl = YoutubeDL({**opts, 'allowed_extractors': ['-all']})
            ydl.add_info_extractor(RefusedChannelIE())
            return ydl

        # What the caller hands in: the sweep's own options, ignoreerrors included.
        try:
            list_flat('refused:dj_a', {'ignoreerrors': True, 'quiet': True}, ydl_factory=factory)
        except ListingFailed as exc:
            assert exc.status == 403, exc
        else:
            raise AssertionError('a refused listing came back as a list')
        print('ok')
        """
    )
    assert output == 'ok'


def _progress_script(exception_class: str) -> str:
    """A two-video playlist whose first download is aborted from a progress hook."""
    return f"""
        from services.downloader import shutdown

        source = os.path.join(WORK, 'source.bin')
        with open(source, 'wb') as handle:
            handle.write(b'x' * 200000)

        class FileVideoIE(InfoExtractor):
            IE_NAME = 'filevideo'
            _VALID_URL = r'filevideo:(?P<id>\\d+)$'
            started = []

            def _real_extract(self, url):
                video_id = self._match_id(url)
                FileVideoIE.started.append(video_id)
                return {{'id': video_id, 'title': 'v' + video_id, 'url': 'file://' + source, 'ext': 'bin'}}

        class FilePlaylistIE(InfoExtractor):
            IE_NAME = 'fileplaylist'
            _VALID_URL = r'fileplaylist:x$'

            def _real_extract(self, url):
                return self.playlist_result(
                    [self.url_result(f'filevideo:{{n}}', FileVideoIE.ie_key(), f'v{{n}}') for n in (1, 2)], 'x', 'x'
                )

        class PlainAbort(Exception):
            pass

        def hook(progress):
            shutdown.request()
            raise {exception_class}('shutting down')

        ydl = YoutubeDL({{
            'allowed_extractors': ['-all'],
            'quiet': True,
            'ignoreerrors': True,
            'enable_file_urls': True,
            'noprogress': True,
            'outtmpl': os.path.join(WORK, '%(id)s.%(ext)s'),
            'progress_hooks': [hook],
        }})
        ydl.add_info_extractor(FilePlaylistIE())
        ydl.add_info_extractor(FileVideoIE())
        try:
            ydl.download(['fileplaylist:x'])
            outcome = 'returned'
        except DownloadCancelled as exc:
            outcome = 'cancelled:' + type(exc).__name__
        print(outcome, ','.join(FileVideoIE.started))
        """


def test_shutting_down_from_a_progress_hook_stops_the_whole_download_call():
    output = run_with_real_ytdlp(_progress_script('shutdown.ShuttingDown'))
    assert output == 'cancelled:ShuttingDown 1', output


def test_a_plain_exception_from_the_hook_is_swallowed_and_the_next_video_starts():
    """The old behaviour, kept as the control: proves the test above can tell the two apart."""
    output = run_with_real_ytdlp(_progress_script('PlainAbort'))
    assert output == 'returned 1,2', output


def test_a_soundcloud_download_is_written_to_a_part_file_and_renamed_before_post_processing():
    """What the archive insert relies on: the post-processor only ever sees the final file.

    `SoundcloudSongProcessor` writes the archive row and runs the tagger, and it is a
    post-processor; yt-dlp renames `<name>.part` before the post-processors run. So a
    download cut off by SIGKILL leaves a `.part` behind and no archive row.
    """
    output = run_with_real_ytdlp(
        """
        use_service_stubs({
            'soundcloud_folder': os.path.join(WORK, 'soundcloud'),
            'soundcloud_archive': os.path.join(WORK, 'archive'),
            'soundcloud_cookies': cookie_file(),
        })
        from services.downloader.account_schedule import AccountSchedule, InMemoryCheckStore
        from services.downloader.rate_state import InMemoryRateStateStore, RateState
        from services.downloader.soundcloud.soundcloud import SoundcloudDownloader
        from services.downloader.timing import load_timing
        from services.downloader.write_offs import InMemoryWriteOffStore, WriteOffs
        from yt_dlp.postprocessor import PostProcessor

        timing = load_timing('soundcloud', overrides={})
        downloader = SoundcloudDownloader(
            timing=timing,
            rate_state=RateState('soundcloud', timing, store=InMemoryRateStateStore()),
            schedule=AccountSchedule('soundcloud', store=InMemoryCheckStore()),
            unavailable=WriteOffs('soundcloud', store=InMemoryWriteOffStore(), retry_days=30),
            notifier=None,
        )
        opts = {
            k: v
            for k, v in downloader.downloader_config['ydl_opts'].items()
            if k != 'format' and not k.startswith(('sleep', 'max_sleep', 'ratelimit'))
        }

        source = os.path.join(WORK, 'source.mp3')
        with open(source, 'wb') as handle:
            handle.write(b'x' * 200000)
        final = os.path.join(WORK, 'out', 'track.mp3')

        class FileTrackIE(InfoExtractor):
            IE_NAME = 'filetrack'
            _VALID_URL = r'filetrack:x$'

            def _real_extract(self, url):
                return {'id': 'track', 'title': 'track', 'url': 'file://' + source, 'ext': 'mp3'}

        temp_names = set()

        def hook(progress):
            if progress.get('tmpfilename'):
                temp_names.add(progress['tmpfilename'])

        seen = {}

        class Inspect(PostProcessor):
            def run(self, info):
                seen['final'] = os.path.exists(final)
                seen['part'] = os.path.exists(final + '.part')
                return [], info

        ydl = YoutubeDL({
            **opts,
            'allowed_extractors': ['-all'],
            'quiet': True,
            'noprogress': True,
            'enable_file_urls': True,
            'outtmpl': os.path.join(WORK, 'out', '%(title)s.%(ext)s'),
            'progress_hooks': [hook],
        })
        ydl.add_info_extractor(FileTrackIE())
        ydl.add_post_processor(Inspect())
        ydl.download(['filetrack:x'])

        assert temp_names == {final + '.part'}, temp_names
        assert seen == {'final': True, 'part': False}, seen
        print('ok')
        """
    )
    assert output == 'ok'


_REDOWNLOAD_PRELUDE = """
        from services.downloader.redownload import ReplaceExistingPP, redownload_opts, staged_opts
        from yt_dlp.postprocessor import PostProcessor

        folder = os.path.join(WORK, 'library', 'Channel')
        os.makedirs(folder)
        target = os.path.join(folder, 'track.mp3')
        with open(target, 'w') as handle:
            handle.write('old')
        source = os.path.join(WORK, 'source.mp3')
        with open(source, 'w') as handle:
            handle.write('new' * 1000)

        class FileTrackIE(InfoExtractor):
            IE_NAME = 'filetrack'
            _VALID_URL = r'filetrack:(?P<id>.+)$'

            def _real_extract(self, url):
                name = self._match_id(url)
                return {'id': 'track', 'title': 'track', 'url': 'file://' + os.path.join(WORK, name), 'ext': 'mp3'}

        seen = {}

        class Tagger(PostProcessor):
            # Stands in for the tagger's post-processor, which runs last.
            def run(self, info):
                seen['path'] = info['filepath']
                with open(info['filepath']) as handle:
                    seen['content'] = handle.read()[:3]
                return [], info

        def ydl(opts, replace=None):
            instance = YoutubeDL({
                'allowed_extractors': ['-all'],
                'quiet': True,
                'noprogress': True,
                'ignoreerrors': True,
                'enable_file_urls': True,
                **opts,
            })
            instance.add_info_extractor(FileTrackIE())
            if replace:
                instance.add_post_processor(ReplaceExistingPP(replace))
            instance.add_post_processor(Tagger())
            return instance

        def content():
            if not os.path.exists(target):
                return None
            with open(target) as handle:
                return handle.read()[:3]
"""


def test_nooverwrites_makes_a_redownload_onto_the_existing_file_a_no_op():
    """The premise of the YouTube redownload bug: yt-dlp finds the file and fetches nothing."""
    output = run_with_real_ytdlp(
        _REDOWNLOAD_PRELUDE
        + """
        ydl({'outtmpl': os.path.join(folder, '%(title)s.%(ext)s'), 'nooverwrites': True}).download(['filetrack:source.mp3'])
        print(content())
        """
    )
    assert output == 'old'


def test_overwriting_in_place_loses_the_file_when_the_download_fails():
    """Why the redownload stages: told to overwrite, yt-dlp deletes the file first."""
    output = run_with_real_ytdlp(
        _REDOWNLOAD_PRELUDE
        + """
        opts = redownload_opts({'outtmpl': os.path.join(folder, '%(title)s.%(ext)s')})
        ydl(opts).download(['filetrack:missing.mp3'])
        print(content())
        """
    )
    assert output == 'None'


def test_a_staged_redownload_replaces_the_file_before_the_tagger_runs():
    output = run_with_real_ytdlp(
        _REDOWNLOAD_PRELUDE
        + """
        with staged_opts({'nooverwrites': True}, target) as opts:
            staging = os.path.dirname(opts['outtmpl'])
            ydl(opts, replace=target).download(['filetrack:source.mp3'])
        assert not os.path.exists(staging), os.listdir(folder)
        assert seen == {'path': target, 'content': 'new'}, seen
        assert os.listdir(folder) == ['track.mp3'], os.listdir(folder)
        print(content())
        """
    )
    assert output == 'new'


def test_a_staged_redownload_that_fails_leaves_the_old_file():
    output = run_with_real_ytdlp(
        _REDOWNLOAD_PRELUDE
        + """
        with staged_opts({}, target) as opts:
            ydl(opts, replace=target).download(['filetrack:missing.mp3'])
        assert seen == {}, seen
        assert os.listdir(folder) == ['track.mp3'], os.listdir(folder)
        print(content())
        """
    )
    assert output == 'old'
