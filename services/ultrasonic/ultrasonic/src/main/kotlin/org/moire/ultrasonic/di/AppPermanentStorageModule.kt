package org.moire.ultrasonic.di

import android.content.Context
import androidx.room.Room
import org.koin.android.ext.koin.androidContext
import org.koin.core.module.dsl.viewModel
import org.koin.core.qualifier.named
import org.koin.dsl.module
import org.moire.ultrasonic.data.AppDatabase
import org.moire.ultrasonic.data.MIGRATION_1_2
import org.moire.ultrasonic.data.MIGRATION_2_1
import org.moire.ultrasonic.data.MIGRATION_2_3
import org.moire.ultrasonic.data.MIGRATION_3_2
import org.moire.ultrasonic.data.MIGRATION_3_4
import org.moire.ultrasonic.data.MIGRATION_4_3
import org.moire.ultrasonic.data.MIGRATION_4_5
import org.moire.ultrasonic.data.MIGRATION_5_4
import org.moire.ultrasonic.data.MIGRATION_5_6
import org.moire.ultrasonic.data.MIGRATION_6_5
import org.moire.ultrasonic.data.MIGRATION_6_7
import org.moire.ultrasonic.data.MIGRATION_7_8
import org.moire.ultrasonic.data.MIGRATION_8_9
import org.moire.ultrasonic.home.FavoritesViewModel
import org.moire.ultrasonic.home.HomeViewModel
import org.moire.ultrasonic.home.RecentActivityStore
import org.moire.ultrasonic.management.ManagementRepository
import org.moire.ultrasonic.management.ManagementViewModel
import org.moire.ultrasonic.model.AlbumListModel
import org.moire.ultrasonic.model.ArtistListModel
import org.moire.ultrasonic.model.ServerSettingsModel
import org.moire.ultrasonic.util.Settings

const val SP_NAME = "Default_SP"
const val DB_FILENAME = "ultrasonic-database"
const val HOME_RECENT_SP_NAME = "home_recent"

/**
 * This Koin module contains registration of classes related to permanent storage
 */
val appPermanentStorage = module {
    single(named(SP_NAME)) { Settings.preferences }

    single {
        Room.databaseBuilder(
            androidContext(),
            AppDatabase::class.java,
            DB_FILENAME
        )
            .addMigrations(MIGRATION_1_2)
            .addMigrations(MIGRATION_2_1)
            .addMigrations(MIGRATION_2_3)
            .addMigrations(MIGRATION_3_2)
            .addMigrations(MIGRATION_3_4)
            .addMigrations(MIGRATION_4_3)
            .addMigrations(MIGRATION_4_5)
            .addMigrations(MIGRATION_5_4)
            .addMigrations(MIGRATION_5_6)
            .addMigrations(MIGRATION_6_5)
            .addMigrations(MIGRATION_6_7)
            .addMigrations(MIGRATION_7_8)
            .addMigrations(MIGRATION_8_9)
            .build()
    }

    single { get<AppDatabase>().serverSettingDao() }

    single {
        RecentActivityStore(
            androidContext().getSharedPreferences(HOME_RECENT_SP_NAME, Context.MODE_PRIVATE)
        )
    }

    viewModel { ServerSettingsModel(get(), get(), get()) }
    viewModel { AlbumListModel(get()) }
    viewModel { ArtistListModel(get()) }
    viewModel { HomeViewModel(get()) }
    viewModel { FavoritesViewModel() }

    single { ManagementRepository(get()) }
    viewModel { ManagementViewModel(get()) }
}
