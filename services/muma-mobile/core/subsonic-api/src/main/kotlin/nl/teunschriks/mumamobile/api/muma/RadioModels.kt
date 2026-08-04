package nl.teunschriks.mumamobile.api.muma

import com.google.gson.annotations.SerializedName

/**
 * Radio timeline models. The server owns an absolute timeline: every entry
 * carries `started_at` in server-clock epoch seconds, so a client works out
 * where playback should be rather than being told a position.
 */
data class RadioChannel(
    val slug: String = "",
    val name: String = "",
    val genre: String? = null
)

data class RadioChannelsResponse(
    val channels: List<RadioChannel> = emptyList()
)

data class RadioEntry(
    @SerializedName("track_id") val trackId: String = "",
    val title: String = "",
    val artist: String = "",
    val album: String = "",
    @SerializedName("cover_art") val coverArt: String? = null,
    @SerializedName("duration_ms") val durationMs: Int = 0,
    @SerializedName("started_at") val startedAt: Double = 0.0,
    @SerializedName("ends_at") val endsAt: Double = 0.0
)

data class RadioStateResponse(
    @SerializedName("server_time") val serverTime: Double = 0.0,
    val channel: RadioChannel = RadioChannel(),
    val current: RadioEntry? = null,
    val next: RadioEntry? = null
)

data class RadioTimeResponse(
    @SerializedName("server_time") val serverTime: Double = 0.0
)
