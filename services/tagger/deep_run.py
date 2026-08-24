"""Cadence for the tagger's deep run.

The tagger skips every file whose mtime it has already recorded. That is what keeps the
five-minute round cheap, and it is also what makes a new rule, a new festival name or a
corrected alias invisible to everything that was tagged before it existed: the file is
never looked at again. Until now the only way out was somebody calling
`POST /api/management/tagger/rescan` or a one-off script such as
`tools/retag_festivals.py`.

The deep run hands a slice of the oldest rows back to the tagger on every round, so the
whole library passes the current rules roughly once every `tagger_deep_run_days`.

**A slice per round rather than one monthly pass.** The tagger holds a single lock, so
flagging the whole library at once would keep freshly downloaded files waiting behind a
sweep that runs for hours. A slice is a few seconds of extra work and never blocks.

**The query is self-limiting.** Only rows whose `last_processed` is older than the window
qualify, and `mark_processed` refreshes that column, so once the library has cycled the
batch comes back empty until rows age again. Sizing the batch is therefore about the peak
cost of one round, not about hitting the window exactly.

Re-tagging an unchanged file is cheap on purpose: `BaseSong.save_file` only writes when a
rule actually produced a different value, so a round that finds nothing new touches no
files on disk and gives LMS nothing to re-index.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from services.common.config_store import ConfigStore as Settings
from services.common.Helpers.ProcessedFilesHelper import ProcessedFilesHelper

logger = logging.getLogger('music-manager.tagger.deep_run')


@lru_cache(maxsize=1)
def _default_helper() -> ProcessedFilesHelper:
    """One helper for the lifetime of the process, created on first use.

    Lazily, because importing this module must not open a database connection: the tagger
    loop imports it at startup, before the database is necessarily reachable.
    """
    return ProcessedFilesHelper()


def _positive(value) -> int:
    """A knob that is missing, unparseable or negative counts as off."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def deep_run_tick(helper: ProcessedFilesHelper | None=None, settings=None) -> int:
    """Queue one slice of the deep run. Returns how many files were handed back.

    Never raises: a database that is briefly away may delay the deep run, but it may not
    stop the ordinary tagging round that follows it.
    """
    settings = settings or Settings()
    days = _positive(settings.get('tagger_deep_run_days'))
    batch = _positive(settings.get('tagger_deep_run_batch'))
    if not days or not batch:
        return 0
    helper = helper or _default_helper()
    marked = 0
    try:
        marked = helper.mark_stale_for_rescan(days, batch)
        if marked:
            logger.info('Deep run queued %d file(s) last tagged over %d days ago, %d still waiting', marked, days, helper.count_stale(days))
    except Exception as e:
        logger.error('Deep run could not queue files: %s', e)
    return marked
