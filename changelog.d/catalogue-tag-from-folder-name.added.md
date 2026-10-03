- **`fix-catalogue-tag-mismatch.sh --from-folder-name` fixes the stale catalogue tags no .nfo
  confirms (#172).** The default mode left 272 releases whose files still hold the whole scene
  folder name as CATALOGNUMBER and where the folder and the .nfo agree on no number (268 without an
  .nfo, 4 whose .nfo names another one). The new mode writes the catalogue number in brackets in
  the folder name (`D-Teq_-_Arcade-(BIR047)-WEB-2012-SRG` gets BIR047), only when it passes
  `services/common/catalogue_number.py`. A folder without a passing bracket is listed with the
  reason and never written. An .nfo that names another number is listed as a conflict with both
  numbers. Dry run by default, a JSON backup before the first write, `--rollback`, and a second
  dry run finds nothing.
<!-- release notes -->
- The catalogue-number repair script can now take the number from the release folder's name for
  releases without a confirming .nfo.
