/*
 * MetaDatabase.kt
 * Copyright (C) 2009-2023 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

@file:Suppress("ktlint:standard:max-line-length")

package nl.teunschriks.mumamobile.data

import androidx.room.AutoMigration
import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.TypeConverter
import androidx.room.TypeConverters
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import com.google.gson.Gson
import java.util.Date
import nl.teunschriks.mumamobile.domain.Album
import nl.teunschriks.mumamobile.domain.Artist
import nl.teunschriks.mumamobile.domain.Index
import nl.teunschriks.mumamobile.domain.MusicFolder
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.domain.TrackArtistRef

/**
 * This database is used to store and cache the ID3 metadata
 */

@Database(
    entities = [
        Artist::class,
        Album::class,
        Track::class,
        Index::class,
        MusicFolder::class
    ],
    autoMigrations = [
        AutoMigration(
            from = 1,
            to = 2
        )
    ],
    exportSchema = true,
    version = 8
)
@TypeConverters(Converters::class)
abstract class MetaDatabase : RoomDatabase() {
    abstract fun artistDao(): ArtistDao

    abstract fun albumDao(): AlbumDao

    abstract fun trackDao(): TrackDao

    abstract fun musicFoldersDao(): MusicFoldersDao

    abstract fun indexDao(): IndexDao
}

class Converters {
    @TypeConverter
    fun fromTimestamp(value: Long?): Date? = value?.let { Date(it) }

    @TypeConverter
    fun dateToTimestamp(date: Date?): Long? = date?.time

    @TypeConverter
    fun fromStringList(list: List<String>?): String? = Gson().toJson(list)

    // Deserialize via Array<String>::class.java instead of an anonymous TypeToken subclass:
    // R8 in full mode can merge away the generic superclass of such anonymous classes, after
    // which TypeToken.getType() throws "... isn't parameterized" in release builds only.
    @TypeConverter
    fun toStringList(data: String?): List<String>? =
        Gson().fromJson(data, Array<String>::class.java)?.toList()

    @TypeConverter
    fun fromArtistRefList(list: List<TrackArtistRef>?): String? = Gson().toJson(list)

    // Deserialize via Array<TrackArtistRef>::class.java for the same R8 reason as toStringList.
    @TypeConverter
    fun toArtistRefList(data: String?): List<TrackArtistRef>? =
        Gson().fromJson(data, Array<TrackArtistRef>::class.java)?.toList()
}

val META_MIGRATION_2_3: Migration = object : Migration(2, 3) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("DROP TABLE `albums`")
        db.execSQL("DROP TABLE `indexes`")
        db.execSQL("DROP TABLE `artists`")
        db.execSQL("DROP TABLE `tracks`")
        db.execSQL("DROP TABLE `music_folders`")
        db.execSQL(
            "CREATE TABLE IF NOT EXISTS `albums` (`id` TEXT NOT NULL, `serverId` INTEGER NOT NULL DEFAULT -1, `parent` TEXT, `album` TEXT, `title` TEXT, `name` TEXT, `discNumber` INTEGER, `coverArt` TEXT, `songCount` INTEGER, `created` INTEGER, `artist` TEXT, `artistId` TEXT, `duration` INTEGER, `year` INTEGER, `genre` TEXT, `starred` INTEGER NOT NULL, `path` TEXT, `closeness` INTEGER NOT NULL, `isDirectory` INTEGER NOT NULL, `isVideo` INTEGER NOT NULL, PRIMARY KEY(`id`, `serverId`))"
        )
        db.execSQL(
            "CREATE TABLE IF NOT EXISTS `indexes` (`id` TEXT NOT NULL, `serverId` INTEGER NOT NULL DEFAULT -1, `name` TEXT, `index` TEXT, `coverArt` TEXT, `albumCount` INTEGER, `closeness` INTEGER NOT NULL, `musicFolderId` TEXT, PRIMARY KEY(`id`, `serverId`))"
        )
        db.execSQL(
            "CREATE TABLE IF NOT EXISTS `artists` (`id` TEXT NOT NULL, `serverId` INTEGER NOT NULL DEFAULT -1, `name` TEXT, `index` TEXT, `coverArt` TEXT, `albumCount` INTEGER, `genre` TEXT, `genres` TEXT, `description` TEXT, `closeness` INTEGER NOT NULL, PRIMARY KEY(`id`, `serverId`))"
        )
        db.execSQL(
            "CREATE TABLE IF NOT EXISTS `music_folders` (`id` TEXT NOT NULL, `name` TEXT NOT NULL, `serverId` INTEGER NOT NULL DEFAULT -1, PRIMARY KEY(`id`, `serverId`))"
        )
        db.execSQL(
            "CREATE TABLE IF NOT EXISTS `tracks` (`id` TEXT NOT NULL, `serverId` INTEGER NOT NULL DEFAULT -1, `parent` TEXT, `isDirectory` INTEGER NOT NULL, `title` TEXT, `album` TEXT, `albumId` TEXT, `artist` TEXT, `artistId` TEXT, `track` INTEGER, `year` INTEGER, `genre` TEXT, `contentType` TEXT, `suffix` TEXT, `transcodedContentType` TEXT, `transcodedSuffix` TEXT, `coverArt` TEXT, `size` INTEGER, `songCount` INTEGER, `duration` INTEGER, `bitRate` INTEGER, `path` TEXT, `isVideo` INTEGER NOT NULL, `starred` INTEGER NOT NULL, `discNumber` INTEGER, `type` TEXT, `created` INTEGER, `closeness` INTEGER NOT NULL, `bookmarkPosition` INTEGER NOT NULL, `userRating` INTEGER, `averageRating` REAL, `name` TEXT, PRIMARY KEY(`id`, `serverId`))"
        )
    }
}
val META_MIGRATION_3_4: Migration = object : Migration(3, 4) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE `tracks` ADD COLUMN `genres` TEXT")
        db.execSQL("ALTER TABLE `tracks` ADD COLUMN `date` TEXT")
        db.execSQL("ALTER TABLE `albums` ADD COLUMN `genres` TEXT")
        db.execSQL("ALTER TABLE `albums` ADD COLUMN `date` TEXT")
    }
}

val META_MIGRATION_4_5: Migration = object : Migration(4, 5) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE `artists` ADD COLUMN `genre` TEXT")
        db.execSQL("ALTER TABLE `artists` ADD COLUMN `description` TEXT")
        db.execSQL("ALTER TABLE `artists` ADD COLUMN `genres` TEXT")
    }
}

val META_MIGRATION_5_6: Migration = object : Migration(5, 6) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE `artists` ADD COLUMN `songCount` INTEGER")
    }
}

// Albums carry a rating now, because rating 5 is what "favorite" means.
val META_MIGRATION_6_7: Migration = object : Migration(6, 7) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE `albums` ADD COLUMN `userRating` INTEGER")
    }
}

// Tracks remember their split artists, their moods and their label, so the track info sheet can
// offer each of them as a way into the library.
//
// NOT NULL DEFAULT '[]', not a plain nullable TEXT: the three entity fields are non-null lists,
// so Room's exported schema marks the columns NOT NULL and refuses to open a database whose
// columns disagree. The default is what gives every row that already exists an empty list.
val META_MIGRATION_7_8: Migration = object : Migration(7, 8) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE `tracks` ADD COLUMN `artists` TEXT NOT NULL DEFAULT '[]'")
        db.execSQL("ALTER TABLE `tracks` ADD COLUMN `moods` TEXT NOT NULL DEFAULT '[]'")
        db.execSQL("ALTER TABLE `tracks` ADD COLUMN `labels` TEXT NOT NULL DEFAULT '[]'")
    }
}
