# Live Station Plays No Music On The Phone

# status: fixed

# reported problem
On 2026-11-06, with app 7.19.0 on production, the live stations gave errors on the phone and no music played. The same three streams played in headless Chromium.

# Possible reason
Diagnostics report 44 (app 7.19.0, Q-dance) shows the cause. The phone has a custom cache folder. `CachedDataSource.open` asks that folder for the stream URL, and `StorageFile` throws `IOException` for a path outside its root. The log has `Open`, then `close false` one millisecond later, then `ExoPlaybackException: Source error`, and the retries repeat this. The line `No cache hit, forwarding call` never comes, so no request left the phone. With the default cache folder the check returns false and the stream plays. `MuMa Radio` also uses an https URL, so it has the same fault on such a phone.

The message of the exception was not in the log, because `onPlayerError` wrote only `error.toString()`. The first analysis of this report named ICY metadata as the cause, without a log. That was wrong: the stream never opened. The missing headers are a separate fault: the text stays in the audio, and the song title does not reach the screen.

# solution
`CachedDataSource.open` does not ask the storage for an http or https URL. `getResponseHeaders()` forwards the headers of the upstream source, and returns nothing for a cached file. `onPlayerError` logs the exception and its cause. `CachedDataSourceHeadersTest` covers all but the log line.
