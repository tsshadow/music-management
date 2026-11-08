- Starting a tag run, a scan, a retag, a parse rerun, a redownload or a track split now needs the `rules.manage` permission, and changing the downloader settings needs `config.manage`. Before, any account could do these (issue #216). `GET /api/config` shows the database settings only to `config.manage`.
- A file path sent to the tag, scan and rerun-parse routes must be inside the library, a label decision must name one folder, and the importer leaves an archive alone when it holds a link to a place outside its own folder (issue #217).

<!-- release notes -->

- Only curators can start tagging and scanning runs. A path outside the library is refused.
