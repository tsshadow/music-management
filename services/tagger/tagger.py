import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from mutagen import MutagenError

from services.common.config_store import ConfigStore as Settings
from services.common.Helpers.BrokenSongHelper import BrokenSongHelper
from services.common.Helpers.Cache import reload as reload_rule_caches
from services.common.Helpers.LmsScanTrigger import lms_scan_trigger
from services.common.Helpers.ProcessedFilesHelper import ProcessedFilesHelper
from services.tagger import download_info, ingestion
from services.tagger.constants import SongTypeEnum
from services.tagger.Song.BaseSong import ExtensionNotSupportedException
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


class Tagger:
    """
    Handles automatic tagging of music files using Mutagen,
    based on their source (Label, SoundCloud, YouTube, etc).
    """

    def __init__(self):
        self.parallel = True
        self.stop_requested = False
        processed_files_helper.create_table()

    def run(
        self, parse_labels=True, parse_soundcloud=True, parse_youtube=True, parse_generic=True, parse_telegram=True
    ):
        """
        Entrypoint for the tagging process.
        Scans various music directories (library_labels, YouTube, SoundCloud, generic) and applies appropriate tag parsing.
        """
        # A run started after a rule change must honour it. The helpers in Cache.py
        # preload at import and this process is a long-lived loop, so without this a
        # rule added today would only take effect after a restart.
        reload_rule_caches()
        self.stop_requested = False
        # What a rule change queued comes first, straight from the table, before any
        # folder is walked. The walk goes EPs, Soundcloud, Youtube, Telegram, generic and
        # starts over at the top on every restart; with five deploys in a night and a
        # queue of 200k, Youtube was not reached for sixteen days while the genre
        # decisions made that morning sat behind it. Whatever this pass finishes stays
        # finished across a restart, because a tagged file is no longer queued.
        self._process_pending()
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
        if parse_soundcloud and (not self.stop_requested):
            self._parse_channel_folders('Soundcloud', SongTypeEnum.SOUNDCLOUD)
        if parse_youtube and (not self.stop_requested):
            self._parse_channel_folders('Youtube', SongTypeEnum.YOUTUBE)
        if parse_telegram and (not self.stop_requested):
            self._parse_channel_folders('Telegram', SongTypeEnum.TELEGRAM)
        if parse_generic and (not self.stop_requested):
            self._parse_generic_folders()
        if self.stop_requested:
            logging.info('Tagging process was interrupted by user')
        # One scan per run, not per file: LMS only reprocesses what changed, so this is
        # cheap, and it is what makes a new or corrected tag show up in the app without
        # waiting for LMS's own schedule. Best effort -- it never raises.
        lms_scan_trigger.trigger()

    #: Rows read from the queue per page. One page is one thread pool: large enough for
    #: the pool to matter, small enough that a stop request is honoured within seconds.
    PENDING_BATCH = 500

    def _process_pending(self):
        """Tag the files a rule change queued, without walking a folder for them."""
        after = ''
        total = 0
        while not self.stop_requested:
            paths = processed_files_helper.pending_paths(self.PENDING_BATCH, after)
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
                with ThreadPoolExecutor(max_workers=16) as executor:
                    futures = {
                        executor.submit(Tagger._parse_worker, str(path), detect_song_type(path).name): path
                        for path in present
                    }
                    for future in as_completed(futures):
                        if self.stop_requested:
                            executor.shutdown(wait=False, cancel_futures=True)
                            break
                        if future.result()[1] == 'SAVED':
                            written.append(futures[future])
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
        if total:
            logging.info('Pending pass handed %d queued file(s) to the tagger', total)

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
        for label in label_folders:
            if self.stop_requested:
                break
            song_type = SongTypeEnum.LABEL if not label.name.startswith('_') else SongTypeEnum.GENERIC
            print(label)
            self.parse_folder(label, song_type)

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
            files = []
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
                with ThreadPoolExecutor(max_workers=16) as executor:
                    futures = [
                        executor.submit(Tagger._parse_worker, str(file), song_type.name, None, extra_info)
                        for file in files
                    ]
                    for future in as_completed(futures):
                        if self.stop_requested:
                            executor.shutdown(wait=False, cancel_futures=True)
                            break
                        written = future.result()[1] == 'SAVED' or written
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
            for subfolder in [f for f in folder.iterdir() if f.is_dir() and (not f.name.startswith('_'))]:
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
                return False
            song = self.parse_song(file, song_type, extra_info)
            processed_files_helper.mark_processed(str(file), mtime)
            return Tagger._was_written(song)
        except KeyboardInterrupt:
            logging.info('KeyboardInterrupt')
            sys.exit(1)
        except (PermissionError, MutagenError, FileNotFoundError, ExtensionNotSupportedException) as e:
            logging.error(f'{type(e).__name__}: {e} -> {file}', exc_info=True)
            broken_song_helper.add(str(file), type(e).__name__)
        except Exception as e:
            logging.error(f'Parse_song failed: {e} -> {file}', exc_info=True)
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
        song = None
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
            processed_files_helper.mark_processed(file, mtime)
            # 'SAVED' when the rules changed a tag and the file was written; 'OK' when the
            # rules ran and found nothing to change. Only the first is news to LMS.
            return (file, 'SAVED' if Tagger._was_written(song) else 'OK')
        except Exception as e:
            # `parse_folder` throws this return value away, and the parallel path is the one
            # production runs -- so without the log line a file that failed every single round
            # is indistinguishable from one that was tagged successfully.
            logging.error(f'Parse_song failed: {e} -> {file}', exc_info=True)
            return (file, f'{type(e).__name__}: {e}')


def detect_song_type(path: Path) -> SongTypeEnum:
    """The source type a file gets from where it lives, the same answer the folder walk gives.

    A label release under the EPs root is LABEL unless its label folder starts with an
    underscore (the import queue), the three platform folders map to their own type, and
    everything else -- Livesets, Podcasts, Top 100, Warm Up Mixes -- is GENERIC.
    """
    try:
        path_obj = path.resolve()
    except (FileNotFoundError, RuntimeError):
        path_obj = path.absolute()
    settings = Settings()
    eps_root = Path(settings.eps_folder_path).resolve()
    music_root = Path(settings.music_folder_path).resolve()
    song_type = SongTypeEnum.GENERIC
    try:
        path_str = str(path_obj)
        if path_str.startswith(str(eps_root)):
            relative = path_obj.relative_to(eps_root)
            if relative.parts and (not relative.parts[0].startswith('_')):
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
