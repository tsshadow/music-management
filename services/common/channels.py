"""What a channel is, and what a label is not.

A file that arrived from SoundCloud, YouTube or Telegram used to be tagged with the platform as its
publisher, and the scanner stores a publisher as a label. That is why `/api/analytics/top-labels`
led with `Soundcloud` (132.037 tracks), `Youtube` (30.779) and `Telegram` (1.556) before the first
real label. `__TODO` and `__Free&none` sat in the same list: one is the import folder's own name
stamped onto a release that never left it, the other is the pile of tracks that have no label at all.

None of those is a record label. Three of them are *channels* -- an account on a platform, which
usually is an artist or a label wearing that platform's clothes -- and two are simply the absence of
a label.

The distinction is drawn here, as pure functions over a path and a publisher, so the scanner, the
backfill and their tests all decide it the same way.
"""

# Folder name at the top of a path -> the platform it identifies. The folder names are what the
# downloaders write and are matched case-insensitively; the values are the `channels.platform` enum.
PLATFORM_FOLDERS = {
    'soundcloud': 'soundcloud',
    'youtube': 'youtube',
    'telegram': 'telegram',
}

# Publishers that name no label at all. `__free&none` is the folder holding music that genuinely has
# no label; `__todo` is the import folder, which the tagger stamps onto anything still sitting in it.
NON_LABEL_PUBLISHERS = {
    '',
    '__todo',
    '__free&none',
    '__free & none',
}


# Top-level folders that hold music with no label at all. `songs` is the pile that genuinely has
# none, `import` is the intake folder. They matter because the tagger derives a label from the
# folders above a file: anything sitting outside the label tree would otherwise have its own root
# stored as a label, which is exactly the mistake the platform folders already made.
NON_LABEL_ROOTS = {
    'songs',
    'import',
}


def _normalize(value: str | None) -> str:
    """Lowercased and trimmed, which is how both sets above are keyed."""
    return (value or '').strip().lower()


def is_label(publisher: str | None) -> bool:
    """Whether a publisher value names an actual record label.

    A platform is not a label even though it arrives in the same tag, and neither is a placeholder.
    Everything else is taken at face value: this decides what a value *is not*, and never invents
    one.
    """
    normalized = _normalize(publisher)
    return normalized not in NON_LABEL_PUBLISHERS and normalized not in PLATFORM_FOLDERS


def channel_from_path(path: str, music_root: str | None = None, delimiter: str = '/') -> tuple[str, str] | None:
    """The `(platform, channel name)` a file arrived through, or None if it did not.

    Read from the path rather than from a tag on purpose. The path is what the downloader actually
    wrote -- `<music root>/Soundcloud/<channel>/<file>` -- so it stays correct for the 160.000 files
    already on disk without retagging a single one of them.

    A platform folder with no channel folder under it yields None: a channel with no name is not
    something worth recording.
    """
    if not path:
        return None

    parts = [part for part in path.split(delimiter) if part]

    root = str(music_root or '').strip(delimiter)
    if root:
        root_parts = [part for part in root.split(delimiter) if part]
        if parts[: len(root_parts)] == root_parts:
            parts = parts[len(root_parts) :]

    for index, part in enumerate(parts):
        platform = PLATFORM_FOLDERS.get(_normalize(part))
        if not platform:
            continue
        # The channel is the folder directly below the platform, and something has to sit below that
        # in turn -- otherwise the "channel" is the track itself, loose in the platform folder.
        if index + 2 < len(parts):
            return (platform, parts[index + 1])
        return None

    return None


def path_can_carry_a_label(path: str, music_root: str | None = None, delimiter: str = '/') -> bool:
    """Whether a label derived from this file's folders means anything.

    The tagger reads a label from the folders above a track, which is right inside the label tree
    and wrong everywhere else: a file under `songs/` or `import/` would have that root stored as its
    label, and a file under a platform folder would have the platform stored. Both are the same
    mistake, so both are refused here rather than in two places.
    """
    parts = [part for part in (path or '').split(delimiter) if part]

    root = str(music_root or '').strip(delimiter)
    if root:
        root_parts = [part for part in root.split(delimiter) if part]
        if parts[: len(root_parts)] == root_parts:
            parts = parts[len(root_parts) :]

    if not parts:
        return False

    first = _normalize(parts[0])
    return first not in NON_LABEL_ROOTS and first not in PLATFORM_FOLDERS


def normalize_channel_name(name: str) -> str:
    """The key a channel is stored under, so one spelling cannot become two channels."""
    return ' '.join(_normalize(name).split())
