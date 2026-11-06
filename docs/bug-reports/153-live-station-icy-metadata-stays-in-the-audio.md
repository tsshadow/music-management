# Live Station Plays No Music On The Phone

# status: analysed

# reported problem
On 2026-11-06, with app 7.19.0 on production, the live stations gave errors on the phone and no music played. The same three streams played in headless Chromium.

# Possible reason
Media3 asks every progressive stream for ICY metadata (`Icy-MetaData: 1`). SLAM, Q-dance and 538 answer with `icy-metaint: 16000` and put a block of text in the MP3 data every 16000 bytes. Media3 reads that header through `DataSource.getResponseHeaders()` to take the text out again.

`CachedDataSource` wraps the HTTP source and did not forward the headers, so Media3 saw an empty map. The text stayed in the audio, about once per second. A damaged frame can make Android's MP3 decoder stop with an error, and the retry then meets the same stream. Chromium sends no `Icy-MetaData` header, so it never gets the text.

This cause comes from the code and from a probe of the streams with the same request headers. Nobody saw the decoder error in a phone log. The song title from the stream could not work either, for the same reason.

# solution
`CachedDataSource.getResponseHeaders()` returns the headers of the upstream source, and nothing for a cached file. `CachedDataSourceHeadersTest` pins that `IcyHeaders.parse` finds the interval through this class. A check on a phone after the release is in issue #214.
