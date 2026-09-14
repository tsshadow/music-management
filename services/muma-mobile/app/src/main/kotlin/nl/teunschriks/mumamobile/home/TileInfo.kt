package nl.teunschriks.mumamobile.home

import androidx.core.graphics.toColorInt
import com.google.gson.Gson
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.util.Settings.maxSongs

val tileInfoColors = listOf(
    "#000000", "#00008B", "#8B0000", "#006400", "#4B0082",
    "#808080", "#2F4F4F", "#A9A9A9", "#800000", "#2C3E50",
    "#8B4513", "#3B3B3B", "#556B2F", "#2F4F4F", "#D2691E",
    "#B22222", "#4C4C4C", "#3A3A3A", "#4E4E4E", "#6A5ACD"
).map { it.toColorInt() }

val genreIconMap: Map<String, Int> = mapOf(
    "Recent Songs" to R.drawable.baseline_music_note_24,
    "Random Songs" to R.drawable.baseline_music_note_24,
    "Recent Livesets" to R.drawable.baseline_music_note_24,
    "Random Livesets" to R.drawable.baseline_music_note_24,
    "Euphoric Hardstyle" to R.drawable.baseline_headset_24,
    "Hardstyle" to R.drawable.baseline_music_note_24,
    "Mainstream Hardstyle" to R.drawable.baseline_music_note_24,
    "Hardstyle Classics" to R.drawable.baseline_music_note_24,
    "Raw Hardstyle" to R.drawable.baseline_local_fire_department_24,
    "Mainstream Hardcore" to R.drawable.baseline_thunderstorm_24,
    "Hardcore" to R.drawable.baseline_bolt_24,
    "Millennium Hardcore" to R.drawable.baseline_headset_24,
    "Industrial Hardcore" to R.drawable.baseline_local_fire_department_24,
    "Uptempo Hardcore" to R.drawable.baseline_thunderstorm_24,
    "Bouncy Uptempo" to R.drawable.baseline_bolt_24,
    "Zaagtempo" to R.drawable.baseline_bolt_24
)

class TileInfo(
    var id: String? = null,
    var pageKey: String = "",
    var title: String = "",
    val genre: List<String>? = null,
    val artists: List<String>? = null,
    val year: List<String>? = null,
    val size: Int = maxSongs,
    val festival: List<String>? = null,
    val festivalLineup: String? = null,
    val label: List<String>? = null,
    val offset: Int = 0,
    val length: String = "short",
    val ratingMin: Int = 0,
    val ratingMax: Int = 5,
    val sortMethod: String = "AddedDesc",
    val minDuration: Int? = null,
    val maxDuration: Int? = null,
    val favorite: Boolean = false
) {
    init {
        if (title == "") title = createDefaultTitle()
    }

    private fun createDefaultTitle(): String = buildString {
        when (sortMethod) {
            "AddedDesc" -> append("Recent ")
            "DateDescAndRelease" -> append("Recent ")
            "Random" -> append("Random ")
            "LastWrittenDesc" -> append("Recent Modified ")
        }

        fun pick(value: List<String>?): String? = value?.filter { it.isNotBlank() && it != "All" }
            ?.takeIf { it.isNotEmpty() }
            ?.let { if (it.size == 1) it.first() else "Multiple" }

        listOfNotNull(pick(artists), pick(festival), pick(label), pick(genre))
            .joinToString(" ")
            .let { if (it.isNotBlank()) append(it) }

        pick(year)?.let { append(" ($it)") }
    }
}

fun TileInfo.toSmartParamsJson(): String {
    val map = mutableMapOf<String, Any?>()
    map["pageKey"] = pageKey
    map["genre"] = genre?.filter { it.isNotBlank() }?.takeIf { it.isNotEmpty() }
    map["artists"] = artists?.filter { it.isNotBlank() }?.takeIf { it.isNotEmpty() }
    map["year"] = year?.filter { it.isNotBlank() }?.takeIf { it.isNotEmpty() }
    map["size"] = size
    map["sortMethod"] = sortMethod
    map["ratingMin"] = ratingMin
    map["ratingMax"] = ratingMax
    map["minDuration"] = minDuration
    map["maxDuration"] = maxDuration
    map["festival"] = festival?.filter { it.isNotBlank() }?.takeIf { it.isNotEmpty() }
    map["festivalLineup"] = festivalLineup?.takeIf { it.isNotBlank() }
    map["favorite"] = favorite
    map["length"] = length.takeIf { it.isNotBlank() }
    return Gson().toJson(map.filterValues { it != null })
}

fun nl.teunschriks.mumamobile.domain.Playlist.toTileInfo(): TileInfo? {
    if (smartParams.isEmpty()) return null
    return try {
        val tile = Gson().fromJson(smartParams, TileInfo::class.java).apply {
            this.id = this@toTileInfo.id
            this.title = this@toTileInfo.name
        }
        tile
    } catch (e: Exception) {
        null
    }
}

fun nl.teunschriks.mumamobile.domain.MumaTile.toTileInfo(): TileInfo? {
    if (smartParams.isEmpty()) return null
    return try {
        val tile = Gson().fromJson(smartParams, TileInfo::class.java).apply {
            this.id = this@toTileInfo.id
            this.title = this@toTileInfo.name
        }
        tile
    } catch (e: Exception) {
        null
    }
}
