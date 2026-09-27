- **28 m4a files no longer fail every hourly scan with "Data too long for column 'title'"** (issue
  #91, bug report 117). Their title, original title or display artist held one value repeated up to
  241 times (3,800+ characters) -- left behind by the m4a `ORIG` atom defect fixed in 0.72.2, where
  every retag added one more copy. The scanner now cuts a value longer than its column to the
  column's character length, stores the file, and queues it for the tagger; the new
  `CollapseRepeatedValuesRule` collapses a repeated title, original title or display artist back to
  one value (the longest for the original title, the most frequent for the others). About 1,900
  more titles carry the same repetition at a length that still fitted; the tagger's deep run
  (every file within 30 days) repairs them. A file whose scan keeps failing is now parked after three failures in a row until it
  changes or the service restarts, instead of logging one error per file per hour for good.
<!-- release notes -->
- Tracks whose title had been repeated hundreds of times over now appear in the library, and the
  repeated titles are cleaned up.
