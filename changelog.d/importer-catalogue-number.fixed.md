- **A festival anthem in a release name was taken for its catalogue number, and a name without one
  got an empty prefix.** `Minus_Militia_And_Nolz_-_Recover_The_Archive_(Official_Hardbass_2026_Anthem)_(Edit)-...`
  became `Official_Hardbass_2026_Anthem - ...` and never reached `EPs/B2S`; 2.663 folders in
  `__TODO` were named ` - <release>`. The Renamer now only accepts something that looks like a
  catalogue number (rule derived from the label tree: it rejects none of the 21.408 prefixes the
  old Renamer produced there) and otherwise leaves the name alone.
  `scripts/prod/person/repair-word-prefixed-import-folders.sh` gives the 2.759 misnamed folders
  their name back (dry run first). Bug report 145.

<!-- release notes -->

- **Releases named after a festival anthem no longer get the anthem as their catalogue number**, and
  a release without a catalogue number keeps its name in the import folder.
