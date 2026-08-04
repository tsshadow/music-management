// Converts Lyrics entity from [nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient]
// to app domain entities.
@file:JvmName("APILyricsConverter")

package nl.teunschriks.mumamobile.domain

import nl.teunschriks.mumamobile.api.subsonic.models.Lyrics as APILyrics

fun APILyrics.toDomainEntity(): Lyrics = Lyrics(
    artist = this@toDomainEntity.artist,
    title = this@toDomainEntity.title,
    text = this@toDomainEntity.text
)
