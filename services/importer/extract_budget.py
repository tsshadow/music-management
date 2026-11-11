"""Stop an archive backend before what it writes fills the import filesystem (issue #231).

patool runs the backend (unrar, unar, 7z) as a child process and waits for it, and nothing
in the archive's own header can be trusted about how much it expands to. So a watcher
thread measures the staging folder while the backend runs, and kills the backend when the
folder grows past its budget or the filesystem's free space drops below a floor. The
staging folder is then removed by the caller, as after any failed extraction.

The check runs every `interval` seconds, so the backend can write up to one interval's
worth past the limit before it is stopped. The free-space floor is what absorbs that.
"""

import logging
import os
import signal
import threading

GIB = 1024**3


class ExtractionTooLarge(Exception):
    """The backend was stopped because its output passed the budget; the message says which."""


def staged_bytes(folder: str) -> int:
    """The bytes of every regular file under `folder`. Links are not followed."""
    total = 0
    for parent, _dirs, files in os.walk(folder):
        for name in files:
            try:
                total += os.lstat(os.path.join(parent, name)).st_size
            except OSError:
                continue
    return total


def free_bytes(folder: str) -> int:
    """The free bytes on the filesystem that holds `folder`."""
    stat = os.statvfs(folder)
    return stat.f_bavail * stat.f_frsize


def child_pids(pid: int) -> set[int]:
    """Every live descendant of `pid`, read from /proc. Empty where /proc is not there."""
    parents: dict[int, int] = {}
    try:
        names = os.listdir('/proc')
    except OSError:
        return set()
    for name in names:
        if not name.isdigit():
            continue
        try:
            with open(f'/proc/{name}/stat', encoding='ascii', errors='replace') as handle:
                # The command name is in brackets and may hold spaces; the parent id is the
                # second field after the closing bracket.
                fields = handle.read().rsplit(')', 1)[1].split()
            parents[int(name)] = int(fields[1])
        except (OSError, IndexError, ValueError):
            continue
    found: set[int] = set()
    todo = [pid]
    while todo:
        parent = todo.pop()
        for child, its_parent in parents.items():
            if its_parent == parent and child not in found:
                found.add(child)
                todo.append(child)
    return found


def kill_new_children(existing: set[int]) -> None:
    """Kill every descendant of this process that was not there when the watch began."""
    for pid in child_pids(os.getpid()) - existing:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            continue


class ExtractionWatch:
    """While the block runs, stop the backend when `folder` passes `max_bytes` or free space
    drops below `min_free_bytes`. A limit of 0 is not checked.

    `exceeded` is empty when the block ran within the budget, else what was passed. Only the
    processes started inside the block are killed, so the importer's other children survive.
    """

    def __init__(self, folder: str, max_bytes: int, min_free_bytes: int, interval: float = 0.5, stop=kill_new_children):
        self.folder = folder
        self.max_bytes = max_bytes
        self.min_free_bytes = min_free_bytes
        self.interval = interval
        self.stop = stop
        self.exceeded = ''
        self._done = threading.Event()
        self._existing: set[int] = set()
        self._thread = threading.Thread(target=self._watch, name='extract-budget', daemon=True)

    def __enter__(self):
        self._existing = child_pids(os.getpid())
        self._thread.start()
        return self

    def __exit__(self, *exc_info):
        self._done.set()
        self._thread.join()
        return False

    def over_budget(self) -> str:
        """What the staging folder or the filesystem has passed, or the empty string."""
        if self.max_bytes:
            used = staged_bytes(self.folder)
            if used > self.max_bytes:
                return f'the extraction passed {self.max_bytes} bytes ({used} written)'
        if self.min_free_bytes:
            free = free_bytes(self.folder)
            if free < self.min_free_bytes:
                return f'free space dropped below {self.min_free_bytes} bytes ({free} left)'
        return ''

    def _watch(self):
        """Measure until the block ends or the budget is passed; then stop the backend."""
        while not self._done.wait(self.interval):
            try:
                exceeded = self.over_budget()
            except OSError as e:
                logging.info('Could not measure %s: %s', self.folder, e)
                continue
            if exceeded:
                self.exceeded = exceeded
                logging.info('Stopping the extraction into %s: %s', self.folder, exceeded)
                self.stop(self._existing)
                return
