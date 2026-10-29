# A Diagnostics Report Sent After A Car Drive Contained Nothing Of The Drive

# status: fixed — the download filter filters, the ring buffer drops verbose lines and repeats, credentials are masked

# reported problem
"Op Android Auto doet de nieuwe knop etc het nog steeds niet. Ik heb diagnostiek gestuurd." Report
37 (app 7.4.1, 2026-09-23) holds 1.453 lines. The current session covers 10:54:47–11:05, the
previous one 08:55–09:03. The drive in between left one line: `CarConnection type changed to 0`,
the car disconnecting. 619 of the lines are `DownloadTask`/`DownloadService`, each cached file
checked about five times, one line every two seconds.

Two more things in the same reports:
- report 34 carries `W/GenreTintCache: Could not read genre tints` 266 times within one second,
  each with its stack trace;
- reports 34 and 35 open with the settings dump, including `staticPassword` and `mumaApiKey` in
  plain text — and the report is uploaded to the server.

# Possible reason
- `DownloadService.removeDownloadedTracksFromList` kept every track. Its `false` answers were the
  values of `let` blocks nobody read, and the lambda always ended in `true`. Every playback change
  asks for the upcoming tracks (`PlaybackService.cacheNextSongs`), so every cached one went to a
  `DownloadTask` again, which found the file and logged "already exists". The check-then-add in
  `downloadAsync` was also not atomic: one file was launched three times in the same millisecond,
  and those tasks raced each other's rename and delete (`Failed to delete .partial`).
- `RingBufferLoggerTree` keeps the last 600 lines of every priority, so whatever is loudest decides
  what a report contains.
- `GenreTintCache` leaves `fetchedAt` unset after a failure so the next lookup retries — and the
  next lookup is the next tile on the same browse level.
- `Util.dumpSettingsToLog` writes every preference value.

# solution
- The filter returns what it means (`DownloadService.stateOnDisk`: pinned or cached files are
  skipped, a cached file asked to be kept still goes to the task that renames it); checking and
  queueing happen under one lock, and `processNextTracks` skips a track already active.
- The per-file download lines are `VERBOSE`, and the ring buffer no longer takes `VERBOSE`. A
  warning repeated within a minute is held back and the next one says how many were
  (`RepeatGate`); a message is cut to 12 lines.
- `GenreTintCache` waits 30 seconds after a failed fetch.
- `LogRedaction` masks credential-named settings in the dump, and redacts the ring buffer and stack
  trace again at upload, because a previous session written by an older build is still sent.
- The car layout is logged as published (`custom layout: CYCLE_RATING(icon=…), …`) and `onConnect`
  names the controller, so the next report after a drive shows whether the buttons left the app.

The Android Auto buttons themselves are not fixed by this; see the open GitLab issues.
