# The App Sends A Signed Cover-Art URL As The Cover-Art Id

# status: fixed

# reported problem
MuMa Mobile sometimes called `getCoverArt` with a whole `getCoverArt` URL as the `id`. The LMS
log showed:

    getCoverArt' with params = {c=Ultrasonic}, {f=json},
    {id=https://music.example.com/rest/getCoverArt?id=art-824661-1786979739&size=512&u=...&t=...&s=...&v=1}

LMS answered "Required parameter 'id' is missing", because the value is not a cover-art id. The
notification, the lock screen and Android Auto then showed no cover. The same log line printed
the user name, the token and the salt from inside the nested URL. LMS also printed the top-level
`t` and `s` of every request it logged, because it redacted only `p`, `password` and `apiKey`.

# Possible reason
The web player owns the queue and gives it to the native player service with `setQueue`
(`services/frontend/src/lib/nativeQueue.js`). Each entry had an `artworkUrl`, which
`Player.svelte` built as a signed `restUrl('/rest/getCoverArt?id=...&size=512&<auth>')`.
`QueueTrack.toTrack()` (`services/muma-mobile/.../capacitor/QueueTrack.kt`) put that URL in
`Track.coverArt`, on the assumption that the image loader treats it as an opaque string. It does
not. `AlbumArtContentProvider` puts `Track.coverArt` in the artwork URI of the media session, and
`ImageLoader.downloadCoverArt` sends it as the `id` of `API.getCoverArt(id, size)`, with a new
signature around it. So the server got `getCoverArt?id=https://...getCoverArt?id=...`.

The URL also stayed on the queued track. That includes the `coverArt` extra of the media item,
the content-provider URI that other apps read, and the debug log line of the provider. So the
user's token and salt went to places a cover-art id goes.

# solution
- The web player sends the cover-art id: each `setQueue` entry has `coverArt` (for example
  `art-824661-1786979739`) and no `artworkUrl`. The bridge no longer gets a URL with
  credentials.
- `QueueTrack.toTrack()` uses `coverArt`. It reads the id from an `artworkUrl` that an older
  web bundle still sends. Any other URL, such as the web fallback picture, gives no cover art.
- `coverArtIdOf()` (`imageloader/CoverArtId.kt`) is the one test of what a cover-art value is. A
  plain id comes back unchanged, an http(s) URL to `getCoverArt` gives its `id`, and any other URL
  gives null. `CoverArtRequestHandler.load` and `ImageLoader.downloadCoverArt` call it before
  they call the API, so a URL is never nested in a new request.
- `redactCredentials()` replaces the values of `u`, `t`, `s`, `p` and `apiKey` in a logged value.
  `AlbumArtContentProvider` uses it for its debug line.
- LMS `parameterMapToDebugString` moved to `ParameterParsing.cpp`. It now also redacts `t` and
  `s`, and the credentials in a value that is a URL itself, plain or percent-encoded.

Tests: `CoverArtIdTest`, `QueueMarshallingTest`, `CoverArtRequestHandlerTest` (app),
`nativeQueue.test.js` (web), `ParameterRedaction` (LMS).
