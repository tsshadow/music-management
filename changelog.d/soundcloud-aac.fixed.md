- SoundCloud downloads work again. Since 2026-10-13 SoundCloud serves only AAC streams, and the
  downloader asked for MP3 only, so every new track failed with "Requested format is not
  available". A track without MP3 now downloads its best AAC stream as `.m4a`, without a transcode.
  The tracks missed since then have no archive row, so the next run picks them up.
