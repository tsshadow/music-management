- Reloading a track through LMS needs an admin, or a MuMa key with the `rules.manage` permission. Before, any listener could start a retag that way (issue #230). The web player shows the reload button to admins only.
- The importer stops extracting an archive when the output passes `import_extract_max_gb` (default 50) or leaves less than `import_extract_min_free_gb` (default 10) free. The archive stays in the import folder as `extraction-too-large` (issue #231).

<!-- release notes -->

- Only admins can reload a track's tags from the player.
- An archive that expands too far is stopped before it fills the disk.
