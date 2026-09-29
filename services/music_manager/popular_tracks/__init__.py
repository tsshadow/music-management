"""External popularity for the "Oude hitjes" feed: which of an artist's tracks the world plays most.

`clients` asks Deezer (keyless) and, when a key is configured, Last.fm for an artist's top
tracks; `matcher` ties those titles to library tracks; `worker` runs both on a schedule and
stores the result in `artist_popular_tracks`. See docs/designs/old-hits-feed/technical.md.
"""
