- **1,314 label releases had a date in their .nfo that the tagger did not read.** `NfoDate` allowed
  no more than 10 characters between a date label and its date, so it skipped labels padded with
  dots to a column: `Date..........: 11.23.2022` (AOV, AOV_INT) and `* street date .........:
  2024-03-17` (JUSTiFY). The date ladder then fell back to the arrival date or the year. The reader
  now allows the dot padding. A padded `Date` stays a rip date, and a padded street, release or store
  date keeps its own rung. Measured on production over the 48,769 .nfo folders of the label tree:
  1,314 folders get a date for the first time. One EDML folder changes from its `Release Date` to
  the `Store Date` above it, which is the same rung. No "Last Updated" stamp or other non-release
  date is read. `migrate_v57` adds the five month-first groups the seed script could not measure
  before (AOV, BMI, CMC, DDS, SCL), so `08.11.2023` from AOV reads as 11 August. Issue #169.

<!-- release notes -->

- **1,314 label releases now get the exact date from their .nfo.** The tagger skipped date lines
  padded with dots, such as `Date..........: 11.23.2022`.
