import logging
import os
from dataclasses import dataclass
from os.path import isfile, join

import mutagen

from services.common import release_nfo
from services.common.import_queue import ImportQueue

AUDIO_EXTENSIONS = ('.mp3', '.flac', '.m4a', '.aac', '.wav')

# Ordered most trustworthy first. The keys are matched case-insensitively against the
# tag names mutagen exposes, which differ per container: Vorbis comments come back
# lowercase, ID3 frames as their four-letter id, and anything written as a free-form
# user frame as "txxx:<name>".
LABEL_SOURCES = (
    ('tag:label', ('label', 'organization'), 90),
    ('tag:publisher', ('publisher',), 80),
    ('tag:tpub', ('tpub',), 80),
    ('tag:txxx-publisher', ('txxx:publisher',), 70),
    # Copyright holds a label often enough to be worth reading and an artist name or a
    # bare year often enough to be worth distrusting.
    ('tag:copyright', ('copyright', 'txxx:copyright'), 40),
)

CATID_KEYS = ('labelno', 'catalognumber', 'txxx:catalognumber', 'catalog number', 'txxx:catalog #')

MAX_CONFIDENCE = 99
AGREEMENT_BONUS = 5
NFO_CONFIDENCE = 30

SYNOLOGY_FOLDER = '@eaDir'


@dataclass(frozen=True)
class LabelProposal:
    label: str | None
    source: str
    confidence: int
    catid: str | None


def blacklist(import_folder_name: str) -> set[str]:
    """
    Values that are never a record label, however confidently they are tagged.

    The import queue's name is in here because the tagger writes the publisher from the
    folder a release sits in, and a release that never left the import folder had the
    import folder's own name stamped in as its label (bug report 030). Both its
    historical name and `import_folder_name` -- what it is called today -- count; see
    `ImportQueue.placeholder_values`. Public because the `__TODO` label repair
    (services/tagger/todo_label_repair.py) must refuse exactly what this refuses.
    """
    return {'', import_folder_name.strip().lower()} | ImportQueue('').placeholder_values()


def read_tags(path) -> dict[str, str]:
    """
    Flatten one file's tags to lowercase name -> first value.

    The only part of this module that touches mutagen, and reached through
    `mutagen.File` rather than a from-import on purpose: test modules that ask for the
    `mutagen` stub of `services/tests/mock_base.py` get a module without `File`, and a
    from-import would fail at import time and take every module importing this one down
    with it.
    """
    try:
        tags = mutagen.File(path)
    except Exception as e:  # noqa: BLE001 - a broken file is data, not a crash
        logging.debug('Could not read tags from %s: %s', path, e)
        return {}
    if tags is None:
        return {}
    flat = {}
    for key, value in dict(tags).items():
        text = value[0] if isinstance(value, list) and value else value
        flat[str(key).lower()] = str(text).strip()
    return flat


def _walk(folder_path: str):
    for dirpath, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if d != SYNOLOGY_FOLDER]
        yield dirpath, sorted(files)


def _audio_files(folder_path: str) -> list[str]:
    found: list[str] = []
    for dirpath, files in _walk(folder_path):
        found.extend(
            join(dirpath, name)
            for name in files
            if name.lower().endswith(AUDIO_EXTENSIONS) and isfile(join(dirpath, name))
        )
    return found


def _label_from_nfo(folder_path: str, refused: set[str]) -> str | None:
    """Last resort: every scene release ships an .nfo, and it usually names the label.

    Read through `release_nfo`, which knows the two-column layouts and the `Company` key
    1.344 of the 6.546 .nfo files in the import queue use instead of `Label`.
    """
    for dirpath, files in _walk(folder_path):
        for name in files:
            if not name.lower().endswith('.nfo'):
                continue
            try:
                with open(join(dirpath, name), 'rb') as handle:
                    label = release_nfo.parse(release_nfo.decode(handle.read(256 * 1024))).label
            except OSError as e:
                logging.debug('Could not read %s: %s', name, e)
                continue
            if label and label.strip().lower() not in refused:
                return label.strip()
    return None


def _label_from_tags(per_file: list[dict[str, str]], refused: set[str]) -> tuple[str, str, int] | None:
    """
    The best label the tags offer, as (label, source, confidence).

    Sources are tried in trust order, so a weak `copyright` never outranks a real
    `label` field. Within one source the value most files agree on wins, and each
    extra file that agrees raises the confidence: a single odd spelling among ten
    tracks is a typo, not a second label.
    """
    for source, keys, confidence in LABEL_SOURCES:
        values = []
        for tags in per_file:
            for key in keys:
                value = tags.get(key, '')
                if value and value.lower() not in refused:
                    values.append(value)
                    break
        if values:
            best = max(set(values), key=values.count)
            agreeing = values.count(best) - 1
            return best, source, min(confidence + agreeing * AGREEMENT_BONUS, MAX_CONFIDENCE)
    return None


def _catid_from_tags(per_file: list[dict[str, str]]) -> str | None:
    for tags in per_file:
        tagged = next((tags[key] for key in CATID_KEYS if tags.get(key)), None)
        if tagged:
            return tagged
    return None


def resolve(
    folder_path: str, import_folder_name: str = '', catid_from_name: str | None = None, tag_reader=read_tags
) -> LabelProposal:
    """
    Propose the record label for one release folder, from the release's own contents.

    Deliberately free of database and settings access so it can be tested against a
    temporary directory, and so a failure to read one release cannot take an import
    run down with it. `tag_reader` is injectable because the suite stubs mutagen out.
    """
    refused = blacklist(import_folder_name)
    per_file = [tag_reader(path) for path in _audio_files(folder_path)]
    catid = _catid_from_tags(per_file) or catid_from_name
    from_tags = _label_from_tags(per_file, refused)
    if from_tags:
        label, source, confidence = from_tags
        return LabelProposal(label, source, confidence, catid)
    from_nfo = _label_from_nfo(folder_path, refused)
    if from_nfo:
        return LabelProposal(from_nfo, 'nfo', NFO_CONFIDENCE, catid)
    return LabelProposal(None, 'none', 0, catid)
