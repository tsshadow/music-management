"""Replacing a library file with a fresh download of the same track, in one rename.

A redownload is asked for from the library page when a file is damaged or was cut
short. Two things kept it from doing that:

* both downloaders ran with yt-dlp's `nooverwrites`/default overwrite rules, and
  yt-dlp answers "has already been downloaded" when the target exists -- a YouTube
  redownload was a no-op that reported success;
* telling yt-dlp to overwrite makes it *delete* the existing file before the new
  one is fetched, so a download that then fails (a 403, a dropped connection)
  leaves the library with no file at all.

So the download goes into a staging folder beside the file it replaces -- on the
same filesystem, which is what makes `os.replace` atomic -- and a post-processor
moves the finished, post-processed file over the old one before the tagger's
post-processor runs. Until that rename the old file is untouched; after it the
tagger, the archive and `announce` all see the library path, never the staging one.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager

from yt_dlp.postprocessor import PostProcessor

#: Set on the info dict once the staged file sits at the library path, so a later
#: post-processor knows the path is final and must not be renamed.
REPLACED_KEY = '__muma_replaced'

#: Prefix of the staging folder. The muma scanner and the tagger's walk skip hidden
#: folders, so the half-finished file is never indexed or tagged under its staging
#: name; the folder is removed whatever happens.
STAGING_PREFIX = '.muma-redownload-'


def redownload_opts(opts: dict) -> dict:
    """The options with yt-dlp told explicitly to overwrite rather than skip.

    `overwrites` is the option yt-dlp reads; `nooverwrites` is its deprecated
    inverse and would be translated into it, so it is dropped rather than left to
    contradict the new value.
    """
    result = dict(opts)
    result.pop('nooverwrites', None)
    result['overwrites'] = True
    return result


@contextmanager
def staged_opts(opts: dict, target: str) -> Iterator[dict]:
    """Yield download options that write into a staging folder beside `target`.

    The folder is created next to the file being replaced and removed afterwards,
    together with anything a failed or interrupted download left in it.
    """
    staging = tempfile.mkdtemp(prefix=STAGING_PREFIX, dir=os.path.dirname(target) or '.')
    try:
        staged = redownload_opts(opts)
        staged['outtmpl'] = os.path.join(staging, '%(id)s.%(ext)s')
        yield staged
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def replace_target(staged: str, target: str) -> str:
    """Move the finished download over `target` and return where it ended up.

    Same extension: one `os.replace`, atomic, so a reader sees the old file or the new
    one and never neither. A different extension (the source now serves another
    format) lands beside the old name and the old file is removed only after the new
    one is in place.
    """
    new_ext = os.path.splitext(staged)[1]
    root, old_ext = os.path.splitext(target)
    final = target if new_ext.lower() == old_ext.lower() else root + new_ext
    os.replace(staged, final)
    if final != target and os.path.exists(target):
        os.remove(target)
        logging.info('Redownload came back as %s; replaced %s', new_ext, target)
    return final


class ReplaceExistingPP(PostProcessor):
    """Moves the staged download over the library file it replaces.

    Added after yt-dlp's own post-processors (audio extraction, thumbnail, metadata),
    which run on the staged file, and before the tagger's, which must see the
    library path.
    """

    def __init__(self, target: str, downloader=None):
        super().__init__(downloader)
        self.target = target

    def run(self, info):
        """Replace the target with the downloaded file and point the info dict at it."""
        staged = info.get('filepath') or info.get('_filename')
        if not staged or not os.path.exists(staged):
            logging.warning('Redownload produced no file to put in place of %s', self.target)
            return [], info
        final = replace_target(staged, self.target)
        logging.info('Redownload replaced %s', final)
        info['filepath'] = final
        info['_filename'] = final
        for entry in info.get('requested_downloads') or []:
            entry['filepath'] = final
            entry['_filename'] = final
        # After the post-processors yt-dlp runs MoveFilesAfterDownloadPP, which moves
        # `filepath` into `__finaldir` -- the folder of the filename template, i.e. the
        # staging folder, which is deleted right after. Pointing it at the library folder
        # makes that move a no-op; anything else still waiting to be moved out of the
        # staging folder (a thumbnail nobody embedded) is left there to be deleted with it.
        info['__finaldir'] = os.path.dirname(final)
        staging = os.path.dirname(os.path.abspath(staged))
        files_to_move = info.get('__files_to_move') or {}
        info['__files_to_move'] = {
            source: destination
            for source, destination in files_to_move.items()
            if os.path.dirname(os.path.abspath(source)) != staging
        }
        info[REPLACED_KEY] = True
        return [], info
