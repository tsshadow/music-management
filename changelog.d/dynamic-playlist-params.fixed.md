- A dynamic playlist accepted any text as its definition, and the track list for it answered 500 on a `size` that was not a number or a definition that was not a JSON object. Create and update now answer 422 for those, and for a `size` outside 1 to 2000; a stored row that is still malformed is read with defaults, and a stored `size` above 2000 is cut to 2000. Clients that send what the web and the phone send today are not affected.
- "Defaults" on the playlist management tab added the four default playlists again on every click: the upsert keyed on `(source, remote_id)`, and `remote_id` is NULL for them, so nothing ever collided. A default the user already has, by name, is now left alone.

<!-- release notes -->

- The default playlists are no longer added again each time you ask for them, and a playlist with an invalid definition is refused instead of failing later.
