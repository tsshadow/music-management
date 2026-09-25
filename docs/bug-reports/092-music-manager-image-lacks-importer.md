# The music-manager image lacked services/importer, so the __TODO label repair answered 500

# status: fixed

# reported problem

On 2026-09-25, right after 0.75.0 went live, the first dry run of the `__TODO` label repair
(`GET /api/tagger/todo-label-repair`, bug report 087) answered `500 Internal Server Error`. The
traceback ended in `services/tagger/todo_label_repair.py`, line 40:

```
from services.importer import label_resolver
ModuleNotFoundError: No module named 'services.importer'
```

# Possible reason

`docker/Dockerfile.music-manager` copies a hand-picked set of packages (`common`, `tagger`,
`scanner`, `downloader`, `music_manager`). The repair deliberately reuses the importer's label
resolver, but `services/importer` was never copied into this image. Every test passed because the
test runner has the whole tree; nothing compared the image's contents with what its code imports.

# solution

The Dockerfile now copies `services/importer/` (its only extra dependency, mutagen, is already in
the image). `tests/ci/test_music_manager_image_packages.py` parses every non-test module of the
packages that run in the container and fails if one imports a `services.<package>` the Dockerfile
does not copy.
