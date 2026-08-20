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
