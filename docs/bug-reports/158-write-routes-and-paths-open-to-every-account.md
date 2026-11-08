# Write Routes And File Paths Open To Every Account

# status: fixed

# reported problem
An external static review (issues #216 and #217) found two gaps in music-manager.

1. Any enabled account could start a full tag run, a full library scan, a retag, a parse rerun, a redownload or a track split, and could change the downloader settings. `GET /api/config` gave every account the database host, port, user and name.
2. The tag-file, scan-file and rerun-parse-path routes used the path from the request as it came. A caller could point the tagger at `/etc/passwd` or at `../`. A label decision used the label text as a folder name, so a label such as `../../tmp` moved a release out of the EPs root. The importer extracted archives without a check for symbolic links, so an archive could place a link to any file in the library.

# Possible reason
The routes were written before RBAC (bug report 037) and kept `verify_api_key` alone, which accepts any enabled account. Nothing failed when a new write route had no permission, so "any login" was the default. The path routes were called only by the workers and LMS, with good paths, so the check was never written.

# solution
- The tag, retag, scan, rerun-parse, redownload and split routes need `rules.manage`. The downloader `POST` routes need `config.manage`. `GET /api/config` returns only `VERSION` to an account without `config.manage`.
- `services/music_manager/tests/test_route_permission_matrix.py` walks every router and fails on a write route that has no `require_*` dependency and is not in its `LOGIN_ONLY` or `PUBLIC` list with a reason.
- `library_paths.require_library_file` turns the LMS spelling into music-manager's and resolves links and `..`. A path outside `music_folder_path`, `eps_folder_path` and the import queue is a `400`.
- `LabelDecisionRequest` accepts only one folder name, and the confirm route checks that the target stays inside `eps_folder_path`.
- The extractor leaves an archive in place with reason `extraction-unsafe` when the extracted tree holds a link to a place outside its own folder.
