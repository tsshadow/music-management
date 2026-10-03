import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from mutagen import MutagenError

from services.common.config_store import ConfigStore as Settings
from services.common.Helpers import RoundScope
from services.common.Helpers.BrokenSongHelper import BrokenSongHelper
from services.common.Helpers.Cache import reload as reload_rule_caches
from services.common.Helpers.LmsScanTrigger import lms_scan_trigger
from services.common.Helpers.ProcessedFilesHelper import ProcessedFilesHelper
from services.common.import_queue import ImportQueue
from services.tagger import download_info, ingestion
from services.tagger.constants import SongTypeEnum
from services.tagger.Song.BaseSong import BaseSong, ExtensionNotSupportedException
from services.tagger.Song.GenericSong import GenericSong
from services.tagger.Song.LabelSong import LabelSong
from services.tagger.Song.SoundcloudSong import SoundcloudSong
from services.tagger.Song.TelegramSong import TelegramSong
from services.tagger.Song.YoutubeSong import YoutubeSong
from services.tagger.tag_registration import register_custom_tag_keys

register_custom_tag_keys()
s = Settings()
parse_mp3 = True
parse_flac = True
parse_m4a = True
parse_wav = False
parse_aac = False
broken_song_helper = BrokenSongHelper()
processed_files_helper = ProcessedFilesHelper()


def _env_number(name: str, default: float, cast=float) -> float:
    """An env override, or the default when it is unset, empty or not a number."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == '':
        return default
    try:
        return cast(raw)
    except ValueError:
        logging.warning('%s=%r is not a number, using %s', name, raw, default)
        return default


#: Worker threads per slice. The tagger runs inside the music-manager process, so these
#: threads share the GIL with uvicorn's event loop. Sixteen CPU-bound workers left the loop
#: with practically no turns: a 32.000-file queue after the 0.67.0 deploy had /health and
#: /api/auth/login timing out for over an hour while LMS answered in milliseconds. Twelve
#: keeps most of the throughput; the pause below is what actually gives the API its turn.
TAGGER_WORKERS = max(1, cast(int, _env_number('TAGGER_WORKERS', 12, int)))

#: Seconds the tagger idles between slices of tagged files, once the pool has drained.
#: With every worker thread parked the event loop owns the GIL and serves whatever queued
#: up. Charged per slice in which a worker parsed something, so an unchanged walk pays nothing.
TAGGER_BATCH_PAUSE = max(0.0, _env_number('TAGGER_BATCH_PAUSE', 0.5))

#: Failed attempts in a row after which a file is parked instead of retried. A file that
#: always raises used to be handed out every five-minute round, forever, with an ERROR --
#: and so an alert -- each time. Between attempts the pending pass backs off (see
#: ProcessedFilesHelper.pending_paths); on the last one the file is parked and one
#: WARNING says so. See docs/bug-reports/051-a-failing-file-is-retried-every-round-forever.md.
TAGGER_PARK_AFTER = int(max(1, _env_number('TAGGER_PARK_AFTER', 5, int)))


def record_failure(file: str, error: BaseException) -> int:
    """Count a failed tagging attempt on the file's queue row and log it once, at the right level.

    The first failure is a WARNING with the traceback: that is news, but one file the
    tagger cannot read is not an outage, and it is retried. A retry that fails again is
    INFO, because the WARNING already said everything and each one becomes an event.
    The failure that parks the file is one more WARNING. No round logs more than one
    WARNING for a file and none logs an ERROR -- except when the attempt could not be
    counted (the database is unreachable), which stays an ERROR. Returns the count.
    """
    try:
        mtime = os.stat(file).st_mtime
    except OSError:
        mtime = 0.0
    attempts = processed_files_helper.mark_failed(file, mtime, TAGGER_PARK_AFTER)
    if not isinstance(attempts, int):
        attempts = 0
    if attempts >= TAGGER_PARK_AFTER:
        logging.warning(
            'Parked %s after %d failed tagging attempts in a row (last: %s: %s); it is retried when the file '
            'changes or a retag is requested',
            file,
            attempts,
            type(error).__name__,
            error,
        )
    elif attempts < 1:
        logging.error(f'Parse_song failed: {error} -> {file}', exc_info=error)
    elif attempts == 1:
        logging.warning(f'Parse_song failed: {error} -> {file}', exc_info=error)
    else:
        logging.info(
            'Parse_song failed again (%d of %d before the file is parked): %s -> %s',
            attempts,
            TAGGER_PARK_AFTER,
            error,
            file,
        )
    return attempts


@dataclass
class RoundStats:
    """What one round did, for the one summary line it logs. Only the round's own thread writes it."""

    #: Files the rules ran on (tagged, written or failed); an up-to-date file is not one.
    tagged: int = 0
    #: Of those, the files that were actually written.
    written: int = 0
    #: Files that turned out to be up to date and were not parsed.
    skipped: int = 0

    def count(self, status: str) -> None:
        """Count one file by the status a worker reported for it (see Tagger._parse_worker)."""
        if status == 'SKIPPED':
            self.skipped += 1
            return
        self.tagged += 1
        if status == 'SAVED':
            self.written += 1


class Tagger:
    """
    Handles automatic tagging of music files using Mutagen,
    based on their source (Label, SoundCloud, YouTube, etc).
    """

    def __init__(self):
        self.parallel = True
        self.stop_requested = False
        #: The worker pool of the running round; None outside one. One pool for the whole
        #: round rather than one per slice, because each worker thread holds its own
        #: database connection for the round (RoundScope) and a thread that exits takes
        #: its connection with it.
        self._pool: ThreadPoolExecutor | None = None
        self._stats = RoundStats()
        processed_files_helper.create_table()

    def run(
        self,
        parse_labels=True,
        parse_soundcloud=True,
        parse_youtube=True,
        parse_generic=True,
        parse_telegram=True,
        walk=True,
    ):
        """
        Entrypoint for the tagging process.

        The queue first, then -- when `walk` is set -- the folders. The queue is where
        everything that announces itself ends up: a decision, a rule, a download the
        worker tagged, a file the scanner found. The walk is the safety net for what
        nobody announced, and the loop runs it once a day rather than every round.
        """
        # A run started after a rule change must honour it. The helpers in Cache.py
        # preload at import and this process is a long-lived loop, so without this a
        # rule added today would only take effect after a restart.
        reload_rule_caches()
        self.stop_requested = False
        started = time.monotonic()
        self._stats = RoundStats()
        # One database connection per thread and one rule stack per song type for the
        # whole round, instead of three to six connects and a fresh rule stack per file.
        # See RoundScope and Song/rule_stack.py, and bug report 063.
        with RoundScope.round_scope() as scope, self._round_pool(scope):
            self._run_round(walk, parse_labels, parse_soundcloud, parse_youtube, parse_generic, parse_telegram)
        self._log_round_summary(time.monotonic() - started, scope.opened)
        # No library-wide LMS scan here. There used to be one after every round, every ~5
        # minutes, and a library-wide scan on LMS takes the better part of an hour: each
        # trigger aborted the one before it, so none ever finished, and the request itself
        # waited for the abort until its timeout ran out (bug report 120). Every folder this
        # round wrote to has already been announced on its own (`notify`, in the queue pass
        # and in the walk), which is what makes a corrected tag show up in the app; LMS's
        # periodic scan covers anything nobody announced.

    def _run_round(self, walk, parse_labels, parse_soundcloud, parse_youtube, parse_generic, parse_telegram):
        """The body of a round: the queue, then the walk when asked for."""
        # What the scanner has indexed and this table has never seen: a file dropped in
        # by hand. Queued with its own reason so it goes after the decisions.
        self._queue_new_library_files()
        # What a rule change queued comes first, straight from the table, before any
        # folder is walked. The walk goes EPs, Soundcloud, Youtube, Telegram, generic and
        # starts over at the top on every restart; with five deploys in a night and a
        # queue of 200k, Youtube was not reached for sixteen days while the genre
        # decisions made that morning sat behind it. Whatever this pass finishes stays
        # finished across a restart, because a tagged file is no longer queued.
        self._process_pending()
        if walk:
            # After the pending pass, so the snapshot already shows those files as done.
            # Held for the walk only: the loop sleeps between rounds and there is no reason
            # to keep 327k rows in memory while it does.
            processed_files_helper.load_snapshot()
            try:
                self._walk(parse_labels, parse_soundcloud, parse_youtube, parse_generic, parse_telegram)
            finally:
                processed_files_helper.drop_snapshot()
        if self.stop_requested:
            logging.info('Tagging process was interrupted by user')

    def _round_pool(self, scope: RoundScope.RoundScope):
        """The worker pool for one round, joined to the round's scope; nothing when serial.

        Used as a context manager: on the way out the pool is shut down and waited for,
        before the round closes the connections its workers hold.
        """
        stack = ExitStack()
        if not self.parallel:
            return stack
        pool = ThreadPoolExecutor(
            max_workers=int(TAGGER_WORKERS), initializer=scope.attach, thread_name_prefix='tagger'
        )
        self._pool = pool

        def shut_down():
            self._pool = None
            pool.shutdown(wait=True, cancel_futures=True)

        stack.callback(shut_down)
        return stack

    def _log_round_summary(self, seconds: float, connects: int) -> None:
        """One line per round with what it cost, so a change in per-file cost shows up in the event log.

        INFO when the round tagged anything; an idle round (the loop runs every five
        minutes and most rounds find an empty queue) is DEBUG, so it does not add a row to
        the events table for nothing.
        """
        stats = self._stats
        per_file = f'{seconds * 1000 / stats.tagged:.0f} ms/file' if stats.tagged else 'n/a ms/file'
        level = logging.INFO if stats.tagged else logging.DEBUG
        logging.log(
            level,
            'Tagging round: %d file(s) tagged (%d written, %d up to date) in %.1fs, %s, %d database connection(s) opened',
            stats.tagged,
            stats.written,
            stats.skipped,
            seconds,
            per_file,
            connects,
        )

    def _walk(self, parse_labels, parse_soundcloud, parse_youtube, parse_generic, parse_telegram):
        logging.info(
            'Starting Tag Step with options: %s, %s, %s, %s, %s',
            parse_labels,
            parse_soundcloud,
            parse_youtube,
            parse_generic,
            parse_telegram,
        )
        if parse_labels and (not self.stop_requested):
            self._parse_label_folders()
            self._parse_import_queue()
        if parse_soundcloud and (not self.stop_requested):
            self._parse_channel_folders('Soundcloud', SongTypeEnum.SOUNDCLOUD)
        if parse_youtube and (not self.stop_requested):
            self._parse_channel_folders('Youtube', SongTypeEnum.YOUTUBE)
        if parse_telegram and (not self.stop_requested):
            self._parse_channel_folders('Telegram', SongTypeEnum.TELEGRAM)
        if parse_generic and (not self.stop_requested):
            self._parse_generic_folders()

    #: Rows read from the queue per page. One page is one thread pool: large enough for
    #: the pool to matter, small enough that a stop request is honoured within seconds.
    PENDING_BATCH = 500

    #: The roots and extensions the walk covers, which is also what the anti-join
    #: against the scanner's table may queue: the scanner indexes Lidarr, Hitzone and
    #: .opus too, and the tagger has no rules for those.
    WALK_FOLDERS = ('Soundcloud', 'Youtube', 'Telegram', 'Livesets', 'Podcasts', 'Top 100', 'Warm Up Mixes')

    def _queue_new_library_files(self) -> int:
        roots = [str(s.eps_folder_path)] + [str(Path(s.music_folder_path) / folder) for folder in self.WALK_FOLDERS]
        queue = ImportQueue.from_settings(s)
        if queue.path and not queue.lies_within(s.eps_folder_path):
            # Moved out of the label tree: still the tagger's to look after, as a generic pile.
            roots.append(queue.path)
        extensions = tuple(
            ext
            for ext, enabled in (('mp3', parse_mp3), ('flac', parse_flac), ('m4a', parse_m4a), ('wav', parse_wav))
            if enabled
        )
        added = processed_files_helper.queue_new_library_files(roots, extensions)
        if added:
            logging.info('Queued %d file(s) the scanner knows and the tagger never saw', added)
        return added

    def _process_pending(self):
        """Tag the queued files, reason by reason, without walking a folder for them."""
        total = 0
        for reason in processed_files_helper.pending_reasons():
            if self.stop_requested:
                break
            total += self._process_pending_reason(reason)
        if total:
            logging.info('Pending pass handed %d queued file(s) to the tagger', total)

    def _process_pending_reason(self, reason: str | None) -> int:
        after = ''
        total = 0
        while not self.stop_requested:
            paths = processed_files_helper.pending_paths(self.PENDING_BATCH, after, reason)
            if not paths:
                break
            after = paths[-1]
            present = []
            for raw in paths:
                path = Path(raw)
                if path.is_file():
                    present.append(path)
                else:
                    processed_files_helper.forget(raw)
            written: list[Path] = []
            if self.parallel and present:
                written = self._tag_in_parallel(present, lambda path: detect_song_type(path).name)
            else:
                for path in present:
                    if self.stop_requested:
                        break
                    if self._try_parse(path, detect_song_type(path)):
                        written.append(path)
            total += len(present)
            # One notify per folder that actually changed, as the walk does; the trigger's
            # queue merges them.
            for folder in dict.fromkeys(str(path.parent) for path in written):
                lms_scan_trigger.notify([folder])
        return total

    #: Files handed to the pool between two pauses. Two per worker keeps every thread busy
    #: for the slice; at the observed ~7 files/s that is a few seconds of tagging, then the
    #: API gets its turn. A whole 500-file page between pauses left it waiting over a minute.
    PARALLEL_SLICE = TAGGER_WORKERS * 2

    def _tag_in_parallel(self, files: list[Path], song_type_name, extra_info=None) -> list[Path]:
        """Tag the files a slice at a time and return the ones that were written.

        `song_type_name` maps a file to the SongTypeEnum *name* the worker expects. After
        each slice in which a worker actually parsed something the tagger pauses, so the
        rules never hold the process for more than a slice at a stretch.
        """
        written: list[Path] = []
        with ExitStack() as stack:
            executor = self._pool
            if executor is None:
                # Called outside a round (a test, a caller of parse_folder): a pool of its own.
                executor = stack.enter_context(ThreadPoolExecutor(max_workers=int(TAGGER_WORKERS)))
            for start in range(0, len(files), self.PARALLEL_SLICE):
                if self.stop_requested:
                    break
                chunk = files[start : start + self.PARALLEL_SLICE]
                parsed = self._tag_slice(executor, chunk, song_type_name, extra_info, written)
                self._breathe(parsed)
        return written

    def _tag_slice(self, executor, chunk: list[Path], song_type_name, extra_info, written: list[Path]) -> bool:
        """Hand one slice to the pool and wait for all of it. True when a worker parsed something.

        On a stop request the files not started yet are cancelled and the running ones
        waited for, so the slice has drained when this returns either way -- which is
        what `_breathe` relies on.
        """
        parsed = False
        futures = {
            executor.submit(Tagger._parse_worker, str(file), song_type_name(file), None, extra_info): file
            for file in chunk
        }
        for future in as_completed(futures):
            if self.stop_requested:
                for pending in futures:
                    pending.cancel()
                wait(futures)
                break
            status = future.result()[1]
            self._stats.count(status)
            parsed = parsed or status != 'SKIPPED'
            if status == 'SAVED':
                written.append(futures[future])
        return parsed

    def _breathe(self, parsed: bool) -> None:
        """Let the API have the process for a moment after a slice of real work.

        The pool has drained by the time this runs, so nothing but uvicorn's loop wants
        the GIL during the pause. Skipped when every file in the slice was up to date and
        on a stop request, so an unchanged walk and a shutdown are not slowed down.
        """
        if parsed and TAGGER_BATCH_PAUSE > 0 and not self.stop_requested:
            time.sleep(TAGGER_BATCH_PAUSE)

    def _parse_label_folders(self):
        """
        Parses the EPS folder which contains label/ep/song hierarchies.
        """
        eps_root = Path(s.eps_folder_path)
        if not eps_root.is_dir():
            # Same treatment _parse_channel_folders already gives a missing platform
            # folder. Without it a share that has not mounted yet raises out of
            # Tagger.run, which kills the background tagger loop for the lifetime of
            # the process -- and /health then reports the whole service degraded over
            # a directory that will be back in a minute.
            logging.warning("EPs folder '%s' does not exist, skipping label folders.", eps_root)
            return
        label_folders = sorted([f for f in eps_root.iterdir() if f.is_dir()])
        # Not every folder here is a label: the import queue sits in this tree (bug report
        # 030 -- its name was written into files as their publisher), and so does __Free&None.
        # ImportQueue is the one place that knows which is which; see bug report 087.
        queue = ImportQueue.from_settings(s)
        for label in label_folders:
            if self.stop_requested:
                break
            song_type = SongTypeEnum.LABEL if queue.is_label_folder(label) else SongTypeEnum.GENERIC
            print(label)
            self.parse_folder(label, song_type)

    def _parse_import_queue(self):
        """Tags the import queue as generic songs when it no longer sits inside the EPs root.

        While it lives at `<eps root>/__TODO` the label walk reaches it and tags it GENERIC. Once
        `import_folder_path` points outside the label tree that walk stops seeing it, and without
        this the releases waiting there would go untagged until the Mover placed them.
        """
        queue = ImportQueue.from_settings(s)
        if not queue.path or queue.lies_within(s.eps_folder_path):
            return
        root = Path(queue.path)
        if root.is_dir() and not self.stop_requested:
            self.parse_folder(root, SongTypeEnum.GENERIC)

    def _parse_channel_folders(self, source_folder: str, song_type: SongTypeEnum):
        """
        Parses folders under a platform-specific directory like SoundCloud or YouTube.

        @param source_folder: Root subfolder under music_folder_path
        @param song_type: Enum describing the song origin
        """
        root = Path(s.music_folder_path) / source_folder
        if not root.exists():
            logging.warning(f"Folder '{root}' does not exist, skipping.")
            return
        for channel in sorted([f for f in root.iterdir() if f.is_dir()]):
            if self.stop_requested:
                break
            self.parse_folder(channel, song_type)

    def _parse_generic_folders(self):
        """
        Parses generic folders like Livesets, Podcasts, Top 100.

        The root itself is handed to parse_folder, which recurses. Walking only the
        subfolders -- as this did before -- skipped every file that sits loose in the
        root, and in Warm Up Mixes that is nearly the whole folder.
        """
        generic_folders = ['Livesets', 'Podcasts', 'Top 100', 'Warm Up Mixes']
        music_root = Path(s.music_folder_path)
        for folder_name in generic_folders:
            if self.stop_requested:
                break
            root_path = music_root / folder_name
            if not root_path.exists():
                continue
            self.parse_folder(root_path, SongTypeEnum.GENERIC)

    def parse_folder(self, folder: Path, song_type: SongTypeEnum, extra_info=None):
        """
        Recursively parses a folder and its subfolders for audio files to tag.

        @param folder: Path object to folder to scan
        @param song_type: Enum to define tag strategy
        @param extra_info:
        """
        if self.stop_requested:
            return
        if folder.is_file():
            self._try_parse(folder, song_type, extra_info)
            return
        if '@eaDir' in str(folder):
            return
        try:
            files: list[Path] = []
            for ext, enabled in {
                'mp3': parse_mp3,
                'flac': parse_flac,
                'wav': parse_wav,
                'm4a': parse_m4a,
                'aac': parse_aac,
            }.items():
                if enabled:
                    # `glob` matches on the name, so a *directory* called
                    # `Some Release (2015).mp3` comes back as a candidate song. Everything
                    # downstream then treats it as a file: `stat()` and `needs_processing`
                    # both succeed on a directory, and it only falls over inside mutagen,
                    # as `IsADirectoryError` wrapped in a `MutagenError`. That is one
                    # `Parse_song failed` per pass, forever, because no tagger run can ever
                    # make a directory readable as audio.
                    files.extend(f for f in folder.glob(f'*.{ext}') if f.is_file())
            written = False
            if self.parallel and files:
                written = bool(self._tag_in_parallel(files, lambda _: song_type.name, extra_info))
            else:
                for file in files:
                    if self.stop_requested:
                        break
                    written = bool(self._try_parse(file, song_type, extra_info)) or written
            if written:
                # One notify per folder, not per file, and only for a folder where a file was
                # actually written. A full run walks every folder and nearly all of them come
                # back unchanged -- this notified each of those anyway, so LMS logged 13.798
                # scan requests in three hours against 7 files saved, and re-read ~1.000 files
                # from the NAS per scan, back to back, for hours. LMS reads a directory at a
                # time, so the folder is the unit, and a folder nothing touched is not news.
                lms_scan_trigger.notify([str(folder)])
            if self.stop_requested:
                return
            # Hidden folders are skipped as the scanner skips them: '.quarantine', and the
            # staging folder a redownload writes into beside the file it replaces
            # (services/downloader/redownload.py), which holds a half-finished download.
            for subfolder in [f for f in folder.iterdir() if f.is_dir() and not f.name.startswith(('_', '.'))]:
                if self.stop_requested:
                    break
                self.parse_folder(subfolder, song_type, extra_info)
        except Exception as e:
            logging.error(f'Error parsing folder {folder}: {e}', exc_info=True)

    def _try_parse(self, file: Path, song_type: SongTypeEnum, extra_info=None) -> bool:
        """Tags one file when it needs it. True only when the file on disk was written."""
        try:
            mtime = file.stat().st_mtime
            if not processed_files_helper.needs_processing(str(file), mtime):
                self._stats.count('SKIPPED')
                return False
            # Counted before the rules run: a file that fails is a file the round paid for.
            self._stats.count('OK')
            song = self.parse_song(file, song_type, extra_info)
            # The mtime *after* the save: a file the tagger itself just wrote has a newer one
            # than the stat above, and storing the old value made it "changed" on the next walk.
            processed_files_helper.mark_processed(str(file), file.stat().st_mtime)
            written = Tagger._was_written(song)
            if written:
                self._stats.written += 1
            return written
        except KeyboardInterrupt:
            logging.info('KeyboardInterrupt')
            sys.exit(1)
        except (PermissionError, MutagenError, FileNotFoundError, ExtensionNotSupportedException) as e:
            record_failure(str(file), e)
            broken_song_helper.add(str(file), type(e).__name__)
        except Exception as e:
            record_failure(str(file), e)
        return False

    @staticmethod
    def _was_written(song) -> bool:
        # `is True`, not truthiness: the answer decides whether LMS gets a scan request, and
        # anything that is not a real "yes" from save_file() must count as "no".
        return getattr(song, 'saved', False) is True

    @staticmethod
    def parse_song(path: Path, song_type: SongTypeEnum, manual_tags: dict[str, str] | None = None, extra_info=None):
        """
        Creates a Song instance to trigger tag parsing logic.

        @param path: Path object to the song
        @param song_type: Type of song source (LABEL, YOUTUBE, etc)
        @param extra_info:
        """
        song: BaseSong | None = None
        if extra_info is None:
            # Only the downloader ever holds yt-dlp's answer, and every pass after it walks
            # the filesystem with nothing in hand. The archive row keeps a pruned copy of
            # that dict, so a retag can see what the download saw instead of guessing again
            # from the filename. Nothing for a label or generic file, without a query.
            extra_info = download_info.stored_info(path, song_type)
        if song_type == SongTypeEnum.LABEL:
            song = LabelSong(str(path))
        elif song_type == SongTypeEnum.YOUTUBE:
            song = YoutubeSong(str(path), extra_info)
        elif song_type == SongTypeEnum.SOUNDCLOUD:
            song = SoundcloudSong(str(path), extra_info)
        elif song_type == SongTypeEnum.TELEGRAM:
            song = TelegramSong(str(path))
        elif song_type == SongTypeEnum.GENERIC:
            song = GenericSong(str(path))
        if song:
            # Before parse(), which is where the rules run and the tags stop being what the
            # file arrived with. INSERT IGNORE inside, so this is a no-op on every pass
            # after the first and never overwrites an earlier, truer answer.
            ingestion.record(song, song_type.name)
            song.parse()
            if manual_tags:
                for tag, value in manual_tags.items():
                    song.tag_collection.add(tag, value)
                song.saved = song.save_file() or song.saved
        return song

    @staticmethod
    def _parse_worker(file: str, song_type_str: str, manual_tags: dict[str, str] | None = None, extra_info=None):
        try:
            path = Path(file)
            mtime = path.stat().st_mtime
            if not processed_files_helper.needs_processing(file, mtime):
                return (file, 'SKIPPED')
            song_type = SongTypeEnum[song_type_str]
            song = Tagger.parse_song(path, song_type, manual_tags, extra_info)
            # After the save, for the same reason as in _try_parse.
            processed_files_helper.mark_processed(file, path.stat().st_mtime)
            # 'SAVED' when the rules changed a tag and the file was written; 'OK' when the
            # rules ran and found nothing to change. Only the first is news to LMS.
            return (file, 'SAVED' if Tagger._was_written(song) else 'OK')
        except Exception as e:
            # `parse_folder` throws this return value away, and the parallel path is the one
            # production runs -- so without the log line a file that failed every single round
            # is indistinguishable from one that was tagged successfully. record_failure is
            # also what backs the file off and, eventually, parks it.
            record_failure(file, e)
            return (file, f'{type(e).__name__}: {e}')


def detect_song_type(path: Path) -> SongTypeEnum:
    """The source type a file gets from where it lives, the same answer the folder walk gives.

    A label release under the EPs root is LABEL unless its folder is not a label -- the import
    queue, or an underscore folder such as __Free&None (`ImportQueue.is_label_folder`) -- the three
    platform folders map to their own type, and everything else -- the import queue wherever it
    lives, Livesets, Podcasts, Top 100, Warm Up Mixes -- is GENERIC.
    """
    try:
        path_obj = path.resolve()
    except (FileNotFoundError, RuntimeError):
        path_obj = path.absolute()
    settings = Settings()
    eps_root = Path(settings.eps_folder_path).resolve()
    music_root = Path(settings.music_folder_path).resolve()
    queue = ImportQueue.from_settings(settings).resolved()
    song_type = SongTypeEnum.GENERIC
    try:
        path_str = str(path_obj)
        if queue.contains(path_obj):
            pass
        elif path_str.startswith(str(eps_root)):
            relative = path_obj.relative_to(eps_root)
            if relative.parts and queue.is_label_folder(eps_root / relative.parts[0]):
                song_type = SongTypeEnum.LABEL
        elif path_str.startswith(str(music_root / 'Soundcloud')):
            song_type = SongTypeEnum.SOUNDCLOUD
        elif path_str.startswith(str(music_root / 'Youtube')):
            song_type = SongTypeEnum.YOUTUBE
        elif path_str.startswith(str(music_root / 'Telegram')):
            song_type = SongTypeEnum.TELEGRAM
    except (ValueError, RuntimeError):
        pass
    return song_type


def TagSingleFile(path: str | Path, extra_info=None):
    """
    Automatically detects the source type of a music file based on its location
    and applies the appropriate tagging rules (SoundCloud, YouTube, Label, etc).

    @param path: Absolute or relative path to the music file.
    @param extra_info: Optional metadata dictionary (e.g., from downloader).
    """
    print('Tagging single file"', path)
    if isinstance(path, str):
        path = Path(path)
    try:
        path_obj = path.resolve()
    except (FileNotFoundError, RuntimeError):
        path_obj = path.absolute()
    song_type = detect_song_type(path_obj)
    logging.info("Auto-detected song type for '%s': %s", path_obj, song_type.name)
    song = Tagger.parse_song(path_obj, song_type, extra_info=extra_info)
    try:
        mtime = path_obj.stat().st_mtime
        processed_files_helper.mark_processed(str(path_obj), mtime)
    except Exception as e:
        logging.error(f'Failed to mark file as processed after tagging: {e}')
    return song
