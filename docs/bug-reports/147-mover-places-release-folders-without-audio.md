# The Mover Places Release Folders That Hold No Audio

# status: fixed

# reported problem
Found on 2026-10-02 while preparing the stale-playlist cleanup of GitLab issue #96 (bug report
121), filed as issue #167. The importer's Mover placed every queue folder with a routable catalogue
number in the label tree, whether or not it still held audio. A release folder whose tracks are
gone keeps its `00-*.m3u`, `.jpg`, `.nfo` and `.sfv`. In the label tree, LMS reports its playlist
as `playlist-all-entries-missing` after every library scan.

Measured read-only on production on 2026-10-03:

- Import queue `/mnt/music/EPs/__TODO`, 5,385 folders: 13 hold no audio, for example
  `HCL116 - Double_Phunq_-_Wizard-(HCL116)-SINGLE-WEB-2026-SRG` (a `.jpg` and an `.m3u`) and
  `Peygan_and_Schlot_-_Hey_Baby-WEB-2026` (an `.m3u`). 12 of them have an LMS playlist row. They
  were still in the queue only because their catalogue number has no label yet, or they have none.
- Label tree `/mnt/music/EPs/<label>/<release>`, 44,502 release folders: 163 hold no audio, mostly
  scene leftovers from 2012 to 2022.

# Possible reason
`Mover.run` asked a folder only whether it had settled and which label its catalogue number names.
Only the Flattener looked at audio (`_holds_audio`), and only to tell a multipack wrapper from a
release.

# solution
The owner chose to delete such a folder (issue #167, option 2): it holds nothing worth keeping.

- `services/common/audio_less_folder.py` decides what "no audio" means, and leans towards keeping.
  A folder is audio-less only when every file anywhere below it is an image, a document or OS
  housekeeping, and there is at least one such file. Audio at any depth, an archive not yet
  extracted (`.zip`, `.rar`, a `.r00` volume), any other file, a symbolic link, an empty or an
  unreadable folder all keep it. The image and document lists are the extractor's, now shared.
- `Mover.run` asks this for every settled queue folder before it looks at the catalogue number. An
  audio-less folder is deleted by `delete_from_queue`, which checks again that the folder sits
  directly in the import queue (`ImportQueue`, resolved paths, never a link) and is still
  audio-less. The Mover then writes an `INFO` event without a push ("Release folder without audio
  deleted", with the files it held), asks LMS to rescan the path, and marks an open label proposal
  for the folder `stale`. A folder that cannot be deleted is still not placed. A dry run only logs.
- `delete-audio-less-release-folders.sh` clears the folders already there:
  the queue by default, the label tree as a separate choice after a person reads the list. Each
  folder is tarred to the prod host before it goes, and its stale `library_media_files` rows are
  backed up and deleted with it.
