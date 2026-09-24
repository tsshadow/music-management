# News Mode

MuMa can play the news of the hour: in Android Auto, in the app and in the web
player, interrupting the music and resuming it afterwards.

## Why MuMa records it

There is no feed to subscribe to. The NOS radio bulletin exists as audio only
inside NPO Luister and behind the Google Assistant voice app; no documented RSS
carries it as an mp3 enclosure. `feeds.nos.nl/nosnieuwsalgemeen` is text with
image enclosures. The podcast feeds that do exist — `met-het-oog-op-morgen`,
`de-dag`, BNR Nieuws Vandaag — are daily or twice daily, which is not "the news
of this hour".

What is reachable is the live stream, so MuMa records the bulletin itself off
`https://icecast.omroep.nl/radio1-bb-mp3` at every full hour.

Two measured facts shape how it does that. A raw byte capture of that stream is
already a valid 192 kbit/s MP3 that mutagen can read, so nothing is transcoded
and ffmpeg is not involved. And icecast bursts a backlog buffer on connect, so
alignment to the top of the hour is forgiving — the tap still opens five seconds
early, because missing the pips is the failure that matters.

## What it stores

A recorder thread inside `music-manager` (`services/music_manager/routers/news.py`,
started next to the radio scheduler) taps the stream for ten minutes at `:00`,
writes it to `/app/data/news` and inserts a row in `news_bulletins`. Ten minutes
covers the extended bulletins at 07:00, 08:00, 12:00 and 18:00 whole.

The newest twelve recordings are kept, roughly 14 MB each, and older ones are
deleted with their files. A capture shorter than a minute is discarded rather
than stored: a truncated bulletin is worse than none, because the button appears
to work and then falls silent.

A recording is written as `<slug>-YYYY-MM-DDTHH-MM-SS.mp3.part` and renamed to
drop the `.part` only once it is whole and long enough. Whatever goes wrong — the
stream drops, mutagen cannot read the result, it is too short, or its row cannot
be stored — no `.part` and no unreferenced `.mp3` is left behind. The name carries
the second, not just the minute: two record-now presses in the same minute used to
share one file and get two rows. Rows keep the name they were stored under, so
older `…THH-MM.mp3` recordings still play.

One source records one capture at a time. Sources due at the same boundary are
captured side by side, at most two at once, and no database connection is held
while a stream is being recorded — only for the short writes before and after.
Deleting a source deletes its recordings from disk as well as its rows.

Bulletins deliberately stay **out** of the music library. Ratings, genre
curation, scan statistics, scrobbles and the tagger all key on that library, and
a dozen news files a day would be noise in every one of them. The cost is that
MuMa serves the audio itself, at `GET /api/news/bulletins/{id}/stream`, with
range support so a client can seek.

## Operating it

Two settings matter, both on the `music-manager` service:

- `NEWS_DATA_PATH` — the host directory holding the recordings. **Set this
  explicitly in the production `.env`.** Production runs docker-compose v1, so
  relying on a default rendering correctly is a gamble that has cost this
  project before.
- `NEWS_DATA_DIR` — where that directory is mounted in the container,
  `/app/data/news`.

Everything else lives in the `news_sources` table and is edited from the News tab
of the management screen: the stream URL, the minute of the hour, the recording
length, how many to keep, and whether recording is on at all. That screen also
shows when the last capture succeeded, the last error if there was one, and a
**record now** button — which is the way to check a change without waiting an
hour.

That button reports that a recording *started*, not that it finished: a capture
takes as long as the recording itself, so the server answers immediately and
records in the background. Holding the request open for ten minutes would time
out at the reverse proxy and report a failure for a capture that succeeded. The
result appears in the bulletin list — the refresh button next to it is there
because a background capture has no way to announce itself — and any failure
lands in `last_error`. Pressing it while that source is already recording answers
409 instead of starting a second capture.

The API refuses settings that cannot work (422): the minute of the hour must be
0–59, the recording length 60–3600 seconds (anything under a minute is discarded
anyway, and more than an hour would run into the next one), the lead 0–300
seconds, and the number to keep 1–1000. A retention of zero used to delete the
bulletin that had just been recorded, and a negative one made pruning fail after
the row was written, so the same hour was captured again under the same name.
The recorder also treats any stored value below one as one.

Adding a second source (BNR, a foreign broadcaster) needs no code: the schema and
the recorder loop already handle several, only the seed carries one.

## Playing it

In Android Auto there is a News node in the browse tree and a news button beside
the transport controls. The button carries no extras, because Android Auto
strips them when the tap comes from the car, so the handler resolves the latest
bulletin itself. Pressing it snapshots the queue, index and position; the
bulletin plays; when it ends the music resumes where it was.

Radio is the exception. A radio channel has no meaningful position — the server
owns that timeline — so a channel that was playing is re-tuned after the
bulletin rather than restored to a position that would be wrong by exactly the
length of the news.

The web player behaves the same way, with one wrinkle: an `<audio>` element
cannot send an `X-API-Key` header, and the endpoint takes the key no other way,
so the browser fetches the bulletin and plays it from a blob.

## Legal position

The recordings stay inside the authenticated private stack, for personal use.
They are not redistributed.
