"""Resolves the label and catalog number a label release carries in its path.

The library layout is `<eps root>/<label>/<cat id - release>/<file>`, so the two folders above
a track name it. Scene releases regularly ship a second copy of the release folder inside itself,
which puts the audio one level deeper; counting parents up from the file then lands on the release
folder and stores that as the label. Anchoring on the EPs root keeps the label at the first
component no matter how deep the file sits below it.
"""

from services.common.catalogue_number import is_catalogue_number


def split(path: str, eps_root: str | None, delimiter: str) -> tuple[str, str]:
    """Returns `(label, release folder)` for a label path.

    Paths outside the EPs root - the importer works on its own folder - fall back to the two
    folders directly above the file, which is what the tagger did before the root was consulted.
    """
    root = str(eps_root or '').rstrip(delimiter)
    if root and path.startswith(root + delimiter):
        parts = [part for part in path[len(root) + 1 :].split(delimiter) if part]
        if len(parts) >= 3:
            return (parts[0], parts[1])
        if len(parts) == 2:
            return (parts[0], '')
        return ('', '')
    parents = path.rsplit(delimiter, 2)
    if len(parents) < 3:
        return ('', '')
    return (parents[0].split(delimiter)[-1], parents[1])


def catalog_number(release_folder: str) -> str:
    """The catalog number is the first space separated part of the release folder.

    A folder name without a space is a catalogue number only when it is nothing else
    (`FUSION001`). The importer prefixes `<cat id> - ` only when the release has one, and
    since bug report 145 it leaves every other name alone -- a whole scene name like
    `Guizcore_-_Coffee_Time-WEB-FLAC-2026` is not a catalogue number.
    """
    if ' ' not in release_folder:
        return release_folder if is_catalogue_number(release_folder) else ''
    return release_folder.split(' ')[0]
