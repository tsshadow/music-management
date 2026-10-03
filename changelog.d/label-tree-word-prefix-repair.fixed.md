- **19 release folders in the label tree still had a festival anthem as their catalogue number.**
  The old Renamer's `Official_Hardbass_2026_Anthem - ...` names also reached `EPs/<label>/`, and
  the tagger wrote the anthem into each file as its catalogue number. `repair-word-prefixed-import-folders.sh --label-tree`
  renames them to the name the Renamer gives today. It moves the stored paths of their files with
  them, so track ids and ratings stay, and it clears a catalogue-number tag that holds exactly the
  word. The label stays the same. It never renames 3 ambiguous folders and lists them for a person
  (`I_Am_Frenchcore_05`, `I_Am_Frenchcore_12`, `NERKOLOG!K40`). Dry run first. Bug report 145.
<!-- release notes -->
- A repair script fixes 19 releases in the label tree that had a festival anthem as their
  catalogue number. Dry run first.
