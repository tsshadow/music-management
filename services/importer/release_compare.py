"""Whether two release folders hold the same release.

Both steps that move a folder need this and neither can afford to be slow about it: the renamer
when its target name is taken, the mover when the label folder already has that release.

The implementation moved to `services/common/Helpers/ReleaseFolder.py`, next to the guarded move
that uses it. Confirming a label proposal moves a release folder too, and that endpoint runs in
the music-manager image, which does not ship `services/importer`. Re-exported here because the
importer's own steps have always reached for it at this address.
"""

from services.common.Helpers.ReleaseFolder import folder_entries, is_same_release

__all__ = ['folder_entries', 'is_same_release']
