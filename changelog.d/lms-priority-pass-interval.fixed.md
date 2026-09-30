- **A new download shows up in LMS within minutes again while a library scan runs.** Priority
  passes for announced folders came about 30 minutes apart on production. The walk was not the
  cause, it checks every 10 files. The check for removed files was: before a pass it finished every
  job in flight and first deleted everything they had found. On production that meant up to 10,000
  image rows at 0.2 s each (the artist portraits under `/mnt/music/artists`, outside LMS's
  library). The deletion now runs 50 rows at a time with a check in between, so a due pass waits
  about 10 s instead of half an hour. One pass also reads at most 50 folders; the rest go in the
  next one (bug report 136).

<!-- release notes -->

- **A new download shows up in LMS within minutes again while a library scan runs.** It could take
  half an hour, while the scan was cleaning up thousands of removed images.
