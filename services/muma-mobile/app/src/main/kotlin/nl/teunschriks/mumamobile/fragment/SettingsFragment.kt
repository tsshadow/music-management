/*
 * SettingsFragment.kt
 * Copyright (C) 2009-2023 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment

import android.content.DialogInterface
import android.content.Intent
import android.content.SharedPreferences
import android.content.SharedPreferences.OnSharedPreferenceChangeListener
import android.net.Uri
import android.os.Bundle
import android.provider.SearchRecentSuggestions
import android.view.View
import androidx.annotation.StringRes
import androidx.core.content.FileProvider
import androidx.navigation.fragment.findNavController
import androidx.preference.CheckBoxPreference
import androidx.preference.EditTextPreference
import androidx.preference.ListPreference
import androidx.preference.Preference
import androidx.preference.PreferenceFragmentCompat
import java.io.File
import kotlin.math.ceil
import org.koin.core.component.KoinComponent
import org.koin.core.component.inject
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.BuildConfig
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.diagnostics.CrashReportManager
import nl.teunschriks.mumamobile.fragment.FragmentTitle.setTitle
import nl.teunschriks.mumamobile.log.FileLoggerTree
import nl.teunschriks.mumamobile.log.FileLoggerTree.Companion.deleteLogFiles
import nl.teunschriks.mumamobile.log.FileLoggerTree.Companion.getLogFileList
import nl.teunschriks.mumamobile.log.FileLoggerTree.Companion.getLogFileNumber
import nl.teunschriks.mumamobile.log.FileLoggerTree.Companion.getLogFileSizes
import nl.teunschriks.mumamobile.log.FileLoggerTree.Companion.plantToTimberForest
import nl.teunschriks.mumamobile.log.FileLoggerTree.Companion.uprootFromTimberForest
import nl.teunschriks.mumamobile.provider.SearchSuggestionProvider
import nl.teunschriks.mumamobile.service.DownloadService
import nl.teunschriks.mumamobile.service.RxBus
import nl.teunschriks.mumamobile.util.AppIconVariant
import nl.teunschriks.mumamobile.util.ConfirmationDialog
import nl.teunschriks.mumamobile.util.Constants
import nl.teunschriks.mumamobile.util.ErrorDialog
import nl.teunschriks.mumamobile.util.FileUtil.ultrasonicDirectory
import nl.teunschriks.mumamobile.util.InfoDialog
import nl.teunschriks.mumamobile.util.SelectCacheActivityContract
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.Settings.id3TagsEnabledOnline
import nl.teunschriks.mumamobile.util.Settings.preferences
import nl.teunschriks.mumamobile.util.Storage
import nl.teunschriks.mumamobile.util.TimeSpanPreference
import nl.teunschriks.mumamobile.util.TimeSpanPreferenceDialogFragmentCompat
import nl.teunschriks.mumamobile.util.Util.toast
import timber.log.Timber

/**
 * Shows main app settings.
 */
@Suppress("TooManyFunctions")
class SettingsFragment :
    PreferenceFragmentCompat(),
    OnSharedPreferenceChangeListener,
    KoinComponent {
    private val activeServerProvider: nl.teunschriks.mumamobile.data.ActiveServerProvider by inject()

    private var style: ListPreference? = null
    private var cacheLocation: Preference? = null
    private var showArtistPicture: CheckBoxPreference? = null
    private var useId3TagsOffline: CheckBoxPreference? = null
    private var resumeOnBluetoothDevice: Preference? = null
    private var pauseOnBluetoothDevice: Preference? = null
    private var debugLogToFile: CheckBoxPreference? = null
    private var customCacheLocation: CheckBoxPreference? = null

    override fun onCreatePreferences(savedInstanceState: Bundle?, rootKey: String?) {
        setPreferencesFromResource(R.xml.settings, rootKey)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        setTitle(this, R.string.menu_settings)
        style = findPreference(getString(R.string.setting_key_style))
        resumeOnBluetoothDevice =
            findPreference(getString(R.string.setting_key_resume_on_bluetooth_device))
        pauseOnBluetoothDevice =
            findPreference(getString(R.string.setting_key_pause_on_bluetooth_device))
        debugLogToFile = findPreference(getString(R.string.setting_key_debug_log_to_file))
        showArtistPicture = findPreference(getString(R.string.setting_key_show_artist_picture))
        useId3TagsOffline = findPreference(getString(R.string.setting_key_id3_tags_offline))
        customCacheLocation = findPreference(getString(R.string.setting_key_custom_cache_location))
        cacheLocation = findPreference(getString(R.string.setting_key_cache_location))

        setupDebugPreferences()
        setupSendDiagnosticsPreference()
        setupClearSearchPreference()
        setupCacheLocationPreference()
        setupBluetoothDevicePreferences()
        setupMumaSyncPrefs()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Get all setting keys and populate the summaries
        Settings.getAllKeys().forEach {
            updatePreferenceSummaries(it)
        }

        updateCustomPreferences()
    }

    override fun onResume() {
        super.onResume()
        preferences.registerOnSharedPreferenceChangeListener(this)
    }

    override fun onPause() {
        super.onPause()
        preferences.unregisterOnSharedPreferenceChangeListener(this)
    }

    override fun onSharedPreferenceChanged(sharedPreferences: SharedPreferences?, key: String?) {
        if (key == null || sharedPreferences == null) return

        Timber.d("Preference changed: %s", key)
        updateCustomPreferences()

        updatePreferenceSummaries(key)

        when (key) {
            getString(R.string.setting_key_hide_media) -> {
                setHideMedia(sharedPreferences.getBoolean(key, false))
            }
            getString(R.string.setting_key_debug_log_to_file) -> {
                setDebugLogToFile(sharedPreferences.getBoolean(key, false))
            }
            getString(R.string.setting_key_id3_tags) -> {
                val enabled = sharedPreferences.getBoolean(key, false)
                showArtistPicture?.isEnabled = enabled
                useId3TagsOffline?.isEnabled = enabled
            }
            getString(R.string.setting_key_app_icon) -> {
                // Not a theme change: the icon lives in the manifest, so nothing on screen
                // needs rebuilding. The toast is the only place the launcher caveat fits --
                // updatePreferenceSummaries overwrites every ListPreference summary with the
                // selected entry.
                context?.let {
                    AppIconVariant.apply(it, AppIconVariant.fromSetting(Settings.appIcon))
                    toast(R.string.settings_app_icon_changed)
                }
            }
            getString(R.string.setting_key_style),
            getString(R.string.setting_key_ui_scale),
            getString(R.string.setting_key_track_list_lines) -> {
                // Theme and scale are baked into the activity's context; the track row layout is
                // chosen when a row is inflated. All three need the activity rebuilt.
                RxBus.themeChangedEventPublisher.onNext(Unit)
            }
            getString(R.string.setting_key_custom_cache_location) -> {
                if (Settings.customCacheLocation) {
                    selectCacheLocation()
                } else {
                    if (Settings.cacheLocationUri != "") setCacheLocation("")
                    setupCacheLocationPreference()
                }
            }
        }
    }

    /**
     * Update preference summaries to reflect the current select item (or entered text) in the UI
     *
     * @param key: The key of the preference to update
     */
    private fun updatePreferenceSummaries(key: String) {
        try {
            when (val pref: Preference? = findPreference(key)) {
                is ListPreference -> {
                    // ListPreference.getSummary() feeds the summary through String.format() to
                    // substitute the selected entry, so a literal % in the entry has to be
                    // escaped. The interface size options ("100%", "75%", ...) contain one, and
                    // an unescaped % throws UnknownFormatConversionException while the row is
                    // being bound - which takes the whole app down when Settings is opened.
                    pref.summary = pref.entry?.toString()?.replace("%", "%%")
                }
                is EditTextPreference -> {
                    if (key == getString(R.string.setting_key_muma_api_key)) {
                        pref.summary = if (pref.text.isNullOrEmpty()) "" else "********"
                    } else {
                        pref.summary = pref.text
                    }
                }
                is TimeSpanPreference -> {
                    pref.summary = pref.text
                }
            }
        } catch (ignored: Exception) {
            // If we have updated a ListPreferences possible values, and the user has now an
            // impossible value, getEntry() will throw an Exception.
        }
    }

    override fun onPreferenceTreeClick(preference: Preference): Boolean {
        if (preference.key == "server_settings") {
            findNavController().navigate(R.id.serverSelectorFragment)
            return true
        }
        return super.onPreferenceTreeClick(preference)
    }

    override fun onDisplayPreferenceDialog(preference: Preference) {
        if (preference is TimeSpanPreference) {
            val dialogFragment = TimeSpanPreferenceDialogFragmentCompat()
            val bundle = Bundle(1)
            bundle.putString("key", preference.getKey())
            dialogFragment.arguments = bundle
            @Suppress("DEPRECATION") // Their own super class uses this call :shrug:
            dialogFragment.setTargetFragment(this, 0)
            dialogFragment.show(
                this.parentFragmentManager,
                "androidx.preference.PreferenceFragment.DIALOG"
            )
        } else {
            super.onDisplayPreferenceDialog(preference)
        }
    }

    private fun setupCacheLocationPreference() {
        if (!Settings.customCacheLocation) {
            cacheLocation?.isVisible = false
            return
        }

        cacheLocation?.isVisible = true
        val uri = Uri.parse(Settings.cacheLocationUri)
        cacheLocation!!.summary = uri.path
        cacheLocation!!.onPreferenceClickListener = Preference.OnPreferenceClickListener {
            selectCacheLocation()
            true
        }
    }

    private fun selectCacheLocation() {
        // Start the activity to pick a directory using the system's file picker.
        selectCacheActivityContract.launch(Settings.cacheLocationUri)
    }

    // Custom activity result contract
    private val selectCacheActivityContract =
        registerForActivityResult(SelectCacheActivityContract()) { uri ->
            // parseResult will return the chosen path as an Uri
            if (uri != null) {
                val contentResolver = UApp.applicationContext().contentResolver
                contentResolver.takePersistableUriPermission(uri, RW_FLAG)
                setCacheLocation(uri.toString())
                setupCacheLocationPreference()
            } else {
                ErrorDialog.Builder(requireContext())
                    .setMessage(R.string.settings_cache_location_error)
                    .show()
                if (Settings.cacheLocationUri == "") {
                    Settings.customCacheLocation = false
                    customCacheLocation?.isChecked = false
                    setupCacheLocationPreference()
                }
            }
        }

    private fun setupBluetoothDevicePreferences() {
        val resumeSetting = Settings.resumeOnBluetoothDevice
        val pauseSetting = Settings.pauseOnBluetoothDevice
        resumeOnBluetoothDevice!!.summary = bluetoothDevicePreferenceToString(resumeSetting)
        pauseOnBluetoothDevice!!.summary = bluetoothDevicePreferenceToString(pauseSetting)
        resumeOnBluetoothDevice!!.onPreferenceClickListener =
            Preference.OnPreferenceClickListener {
                showBluetoothDevicePreferenceDialog(
                    R.string.settings_playback_resume_on_bluetooth_device,
                    Settings.resumeOnBluetoothDevice
                ) { choice: Int ->
                    Settings.resumeOnBluetoothDevice = choice
                    resumeOnBluetoothDevice!!.summary = bluetoothDevicePreferenceToString(choice)
                }
                true
            }
        pauseOnBluetoothDevice!!.onPreferenceClickListener =
            Preference.OnPreferenceClickListener {
                showBluetoothDevicePreferenceDialog(
                    R.string.settings_playback_pause_on_bluetooth_device,
                    Settings.pauseOnBluetoothDevice
                ) { choice: Int ->
                    Settings.pauseOnBluetoothDevice = choice
                    pauseOnBluetoothDevice!!.summary = bluetoothDevicePreferenceToString(choice)
                }
                true
            }
    }

    private fun showBluetoothDevicePreferenceDialog(
        @StringRes title: Int,
        defaultChoice: Int,
        onChosen: (Int) -> Unit
    ) {
        val choice = intArrayOf(defaultChoice)
        ConfirmationDialog.Builder(requireContext()).setTitle(title)
            .setSingleChoiceItems(
                R.array.bluetoothDeviceSettingNames,
                defaultChoice
            ) { _: DialogInterface?, i: Int -> choice[0] = i }
            .setNegativeButton(R.string.common_cancel) { dialogInterface: DialogInterface, _: Int ->
                dialogInterface.cancel()
            }
            .setPositiveButton(R.string.common_ok) { dialogInterface: DialogInterface, _: Int ->
                onChosen(choice[0])
                dialogInterface.dismiss()
            }
            .create().show()
    }

    private fun bluetoothDevicePreferenceToString(preferenceValue: Int): String = when (preferenceValue) {
        Constants.PREFERENCE_VALUE_ALL -> {
            getString(R.string.settings_playback_bluetooth_all)
        }
        Constants.PREFERENCE_VALUE_A2DP -> {
            getString(R.string.settings_playback_bluetooth_a2dp)
        }
        Constants.PREFERENCE_VALUE_DISABLED -> {
            getString(R.string.settings_playback_bluetooth_disabled)
        }
        else -> ""
    }

    private fun setupDebugPreferences() {
        val debugCategory = findPreference<androidx.preference.PreferenceCategory>("settings.debug.category")
        if (!BuildConfig.DEBUG) {
            debugCategory?.isVisible = false
        } else {
            findPreference<Preference>(getString(R.string.setting_key_view_log))?.onPreferenceClickListener =
                Preference.OnPreferenceClickListener {
                    viewLog()
                    true
                }
            findPreference<Preference>(getString(R.string.setting_key_share_log))?.onPreferenceClickListener =
                Preference.OnPreferenceClickListener {
                    shareLog()
                    true
                }
        }
    }

    /**
     * Not part of [setupDebugPreferences] on purpose: the debug category is hidden in release
     * builds, and sending diagnostics after a failed call is exactly what a release user needs.
     */
    private fun setupSendDiagnosticsPreference() {
        findPreference<Preference>(getString(R.string.setting_key_send_diagnostics))
            ?.onPreferenceClickListener = Preference.OnPreferenceClickListener {
            CrashReportManager.sendManualReport(requireContext())
            true
        }
    }

    private fun shareLog() {
        val logFiles = getLogFileList()
        if (logFiles.isNullOrEmpty()) {
            toast(R.string.settings_debug_log_deleted)
            return
        }
        logFiles.sortByDescending { it.lastModified() }
        val latestLog = logFiles[0]

        val uri = FileProvider.getUriForFile(
            requireContext(),
            "${requireContext().packageName}.fileprovider",
            latestLog
        )

        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_STREAM, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        startActivity(Intent.createChooser(intent, getString(R.string.settings_debug_share_log)))
    }

    private fun viewLog() {
        findNavController().navigate(R.id.logViewerFragment)
    }

    private fun setupClearSearchPreference() {
        val clearSearchPreference =
            findPreference<Preference>(getString(R.string.setting_key_clear_search_history))
        if (clearSearchPreference != null) {
            clearSearchPreference.onPreferenceClickListener =
                Preference.OnPreferenceClickListener {
                    val suggestions = SearchRecentSuggestions(
                        activity,
                        SearchSuggestionProvider.AUTHORITY,
                        SearchSuggestionProvider.MODE
                    )
                    suggestions.clearHistory()
                    toast(R.string.settings_search_history_cleared)
                    false
                }
        }
    }

    private fun updateCustomPreferences() {
        if (debugLogToFile?.isChecked == true) {
            debugLogToFile?.summary = getString(
                R.string.settings_debug_log_path,
                ultrasonicDirectory,
                FileLoggerTree.FILENAME
            )
        } else {
            debugLogToFile?.summary = ""
        }

        showArtistPicture?.isEnabled = id3TagsEnabledOnline
        useId3TagsOffline?.isEnabled = id3TagsEnabledOnline
    }

    private fun setHideMedia(hide: Boolean) {
        // TODO this only hides the media files in the Ultrasonic dir and not in the music cache
        val nomediaDir = File(ultrasonicDirectory, ".nomedia")
        if (hide && !nomediaDir.exists()) {
            if (!nomediaDir.mkdir()) {
                Timber.w("Failed to create %s", nomediaDir)
            }
        } else if (nomediaDir.exists()) {
            if (!nomediaDir.delete()) {
                Timber.w("Failed to delete %s", nomediaDir)
            }
        }
        toast(R.string.settings_hide_media_toast, false)
    }

    private fun setCacheLocation(path: String) {
        if (path != "") {
            val uri = Uri.parse(path)
            cacheLocation!!.summary = uri.path ?: ""
        }

        Settings.cacheLocationUri = path

        // Clear download queue.
        DownloadService.clearDownloads()
        Storage.reset()
        Storage.checkForErrorsWithCustomRoot()
    }

    private fun setupMumaSyncPrefs() {
    }


    private fun setDebugLogToFile(writeLog: Boolean) {
        if (writeLog) {
            plantToTimberForest()
            Timber.i("Enabled debug logging to file")
        } else {
            uprootFromTimberForest()
            Timber.i("Disabled debug logging to file")
            val fileNum = getLogFileNumber()
            val fileSize = getLogFileSizes()
            val message = getString(
                R.string.settings_debug_log_summary,
                fileNum.toString(),
                ceil(fileSize.toDouble() / 1000 / 1000).toString(),
                ultrasonicDirectory
            )
            val keep = R.string.settings_debug_log_keep
            val delete = R.string.settings_debug_log_delete
            ConfirmationDialog.Builder(requireContext())
                .setMessage(message)
                .setNegativeButton(keep) { dIf: DialogInterface, _: Int ->
                    dIf.cancel()
                }
                .setPositiveButton(delete) { dIf: DialogInterface, _: Int ->
                    deleteLogFiles()
                    Timber.i("Deleted debug log files")
                    dIf.dismiss()
                    InfoDialog.Builder(requireContext())
                        .setMessage(R.string.settings_debug_log_deleted)
                        .setPositiveButton(R.string.common_ok) { dIf2: DialogInterface, _: Int ->
                            dIf2.dismiss()
                        }
                        .create().show()
                }
                .create().show()
        }
    }

    companion object {
        const val RW_FLAG = Intent.FLAG_GRANT_READ_URI_PERMISSION or
            Intent.FLAG_GRANT_WRITE_URI_PERMISSION
        const val PERSISTABLE_FLAG = Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
    }
}
