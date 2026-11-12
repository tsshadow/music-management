<script>
  import "./density.css";
  import { t } from '../i18n/index.js';
  import { onMount } from 'svelte';
  import { SvelteURLSearchParams } from 'svelte/reactivity';
  import {
    deduplicateEnabled,
    memoriesOnHomeEnabled,
    wrappedOnHomeEnabled,
    trackPageSize,
    TRACK_PAGE_SIZES,
    authParams,
    credentials,
    restUrl,
    homeShortcutCount,
    homeListCount,
    separateHomeHistory,
    homeModeReleaseRadar,
    homeModeDailyMix,
    homeCountDailyMix,
    homeModeFavorites,
    homeCountFavorites,
    homeModeShortcuts,
    homeModeRecentlyReleased,
    homeModeRecentlyAdded,
    showTrackNumber,
    trackListLines,
    displayBitrateWithArtist,
    discSort,
    genreTrackLimit,
    showConfirmationDialog
  } from '../store.js';
  import { platform } from '../platform/index.js';
  import LanguageSetting from './LanguageSetting.svelte';

  // Only where downloads exist. A browser has no files to keep, so a "wifi only"
  // switch there would promise something nothing does; the row below never renders
  // without this, which is also why it is the only place this setting lives -- there
  // used to be a second, account-synced `downloadsWifiOnly` store for a browser that
  // cannot get here, and nothing ever read it.
  const downloadsSupported = platform.storage.supported;

  // The one source of truth for this setting is the real Kotlin preference
  // (`Settings.isWifiRequiredForDownload`, written through `wifiOnly`). The same row
  // also lives on the device-settings tab (`DeviceSettings.svelte`); the two read the
  // same underlying preference, they just do not share a live subscription, so a
  // change on one only appears on the other after a reload of this page.
  let nativeWifiOnly = $state(false);

  // Server default for uiArtistReleaseSortMethod (ReleaseSortMethod::OriginalDateDesc).
  const DEFAULT_SORT_METHOD = 8;

  let settings = $state({
    uiArtistReleaseSortMethod: DEFAULT_SORT_METHOD,
    uiEnableInlineArtistRelationships: false,
    uiInlineArtistRelationships: [2, 6], // Composer, Performer
    feedbackBackend: 0,
    listenbrainzToken: '',
    subsonicEnableTranscodingByDefault: false,
    subsonicDefaultTranscodeFormat: 2,
    subsonicDefaultTranscodeBitrate: 128000,
    subsonicArtistListMode: 0
  });

  let isLoading = $state(true);
  let isSaving = $state(false);
  let message = $state('');
  let isError = $state(false);

  const artistRoles = [
    { id: 1, labelKey: 'role.arranger' },
    { id: 2, labelKey: 'role.composer' },
    { id: 3, labelKey: 'role.conductor' },
    { id: 4, labelKey: 'role.lyricist' },
    { id: 5, labelKey: 'role.mixer' },
    { id: 6, labelKey: 'role.performer' },
    { id: 7, labelKey: 'role.producer' },
    { id: 9, labelKey: 'role.remixer' },
    { id: 10, labelKey: 'role.writer' }
  ];

  /**
   * Reads an integer attribute, falling back only when it is absent or
   * unparseable -- a legitimate 0 must survive.
   *
   * @param {unknown} value
   * @param {number} fallback
   * @returns {number}
   */
  function toInt(value, fallback) {
    const parsed = parseInt(value);
    return Number.isNaN(parsed) ? fallback : parsed;
  }

  function toBool(value) {
    return value === true || value === 'true';
  }

  onMount(async () => {
    await fetchSettings();
    if (downloadsSupported) await loadNativeWifiOnly();
  });

  async function loadNativeWifiOnly() {
    try {
      const device = await platform.system.getSettings();
      nativeWifiOnly = device?.wifiOnly === true;
    } catch (e) {
      console.error("Failed to load the device's wifi-only setting", e);
    }
  }

  /** Writes the real Kotlin setting; this row never renders without `downloadsSupported`. */
  async function toggleWifiOnly() {
    if (!downloadsSupported) return;
    const next = !nativeWifiOnly;
    nativeWifiOnly = next;
    try {
      await platform.system.setSetting({ key: 'wifiOnly', value: next });
    } catch (e) {
      nativeWifiOnly = !next;
      console.error("Failed to save the device's wifi-only setting", e);
    }
  }

  async function fetchSettings() {
    isLoading = true;
    try {
      const resp = await fetch(restUrl(`/rest/getUser?${$authParams}&username=${encodeURIComponent($credentials.username)}`));
      const data = await resp.json();
      const user = data['subsonic-response']?.user;
      if (user) {
        settings = {
          uiArtistReleaseSortMethod: toInt(user.uiArtistReleaseSortMethod, DEFAULT_SORT_METHOD),
          uiEnableInlineArtistRelationships: toBool(user.uiEnableInlineArtistRelationships),
          uiInlineArtistRelationships: (user.uiInlineArtistRelationships || '')
            .split(',')
            .map((s) => parseInt(s))
            .filter((n) => !isNaN(n)),
          feedbackBackend: toInt(user.feedbackBackend, 0),
          listenbrainzToken: user.listenbrainzToken || '',
          subsonicEnableTranscodingByDefault: toBool(user.subsonicEnableTranscodingByDefault),
          subsonicDefaultTranscodeFormat: toInt(user.subsonicDefaultTranscodeFormat, 2),
          subsonicDefaultTranscodeBitrate: toInt(user.subsonicDefaultTranscodeBitrate, 128000),
          subsonicArtistListMode: toInt(user.subsonicArtistListMode, 0)
        };
      }
    } catch (e) {
      console.error('Failed to fetch user settings', e);
    } finally {
      isLoading = false;
    }
  }

  async function saveSettings() {
    isSaving = true;
    message = '';
    isError = false;
    try {
      const params = new SvelteURLSearchParams();
      params.append('username', $credentials.username);

      Object.entries(settings).forEach(([k, v]) => {
        if (Array.isArray(v)) {
          params.append(k, v.join(','));
        } else {
          params.append(k, v);
        }
      });

      const resp = await fetch(restUrl(`/rest/updateUser?${$authParams}&${params.toString()}`));
      const data = await resp.json();
      if (data['subsonic-response']?.status === 'ok') {
        message = $t('settings.saved');
        setTimeout(() => (message = ''), 3000);
      } else {
        isError = true;
        message = $t('settings.saveFailed', { message: data['subsonic-response']?.error?.message || $t('common.unknownError') });
      }
    } catch (e) {
      isError = true;
      message = $t('settings.saveNetworkError');
      console.error(e);
    } finally {
      isSaving = false;
    }
  }

  function toggleDeduplicate() {
    deduplicateEnabled.update((v) => !v);
  }

  /** Shows or hides the memories row on the home screen. */
  function toggleMemoriesOnHome() {
    memoriesOnHomeEnabled.update((v) => !v);
  }

  /** Shows or hides the seasonal Wrapped tile on the home screen. */
  function toggleWrappedOnHome() {
    wrappedOnHomeEnabled.update((v) => !v);
  }

  // homeSectionModeValues; OFF hides the section, BUTTON puts it in the shortcuts grid, OVERVIEW
  // gives it its own heading. Ported from the legacy home_mode_* preferences -- see
  // docs/designs/universal-ui/functional.md, "Device settings".
  const HOME_MODE_OPTIONS = [
    { value: 'OFF', labelKey: 'settings.general.home.modeOff' },
    { value: 'BUTTON', labelKey: 'settings.general.home.modeButton' },
    { value: 'OVERVIEW', labelKey: 'settings.general.home.modeOverview' }
  ];
  const HOME_COUNT_STEPS = [2, 4, 6, 8, 10];
  const TRACK_LIST_LINES_OPTIONS = [
    { value: 2, labelKey: 'settings.general.display.trackListLinesCompact' },
    { value: 3, labelKey: 'settings.general.display.trackListLinesDetailed' }
  ];

  function toggleRole(roleId) {
    if (settings.uiInlineArtistRelationships.includes(roleId)) {
      settings.uiInlineArtistRelationships = settings.uiInlineArtistRelationships.filter((id) => id !== roleId);
    } else {
      settings.uiInlineArtistRelationships = [...settings.uiInlineArtistRelationships, roleId];
    }
  }
</script>

<div class="settings-density p-0 max-w-4xl mx-auto pb-24">
  <header class="mb-8 flex justify-between items-end gap-4">
    <div class="min-w-0">
      <h1 class="text-3xl font-bold mb-2">{$t('settings.general.title')}</h1>
      <p class="text-muma-spotify-text">{$t('settings.general.subtitle')}</p>
    </div>
    <button
      onclick={saveSettings}
      disabled={isSaving || isLoading}
      class="bg-brand text-black font-bold py-3 px-8 rounded-full hover:scale-105 transition-transform disabled:opacity-50 disabled:hover:scale-100 whitespace-nowrap shrink-0"
    >
      {isSaving ? $t('common.saving') : $t('common.saveChanges')}
    </button>
  </header>

  {#if message}
    <div
      class="mb-6 p-4 rounded text-center font-medium {isError
        ? 'bg-red-500/10 border border-red-500/20 text-red-400'
        : 'bg-brand/10 border border-brand/20 text-brand'}"
    >
      {message}
    </div>
  {/if}

  <div class="flex flex-col gap-6">
    <!-- Interface Section -->
    <section class="bg-muma-spotify-panel rounded-lg p-6 shadow-lg border border-white/5">
      <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.general.interface')}</h2>

      <div class="flex flex-col gap-6">
        <LanguageSetting />

        <div class="flex items-center justify-between">
          <div class="flex flex-col gap-1">
            <h3 class="text-lg font-bold">{$t('settings.general.dedupe')}</h3>
            <p class="text-sm text-muma-spotify-text">{$t('settings.general.dedupeHelp')}</p>
          </div>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" class="sr-only peer" checked={$deduplicateEnabled} onchange={toggleDeduplicate}>
            <div class="w-11 h-6 bg-muma-spotify-hover peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
          </label>
        </div>

        <div class="flex items-center justify-between">
          <div class="flex flex-col gap-1">
            <h3 class="text-lg font-bold">{$t('settings.general.memoriesOnHome')}</h3>
            <p class="text-sm text-muma-spotify-text">{$t('settings.general.memoriesOnHomeHelp')}</p>
          </div>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" class="sr-only peer" checked={$memoriesOnHomeEnabled} onchange={toggleMemoriesOnHome}>
            <div class="w-11 h-6 bg-muma-spotify-hover peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
          </label>
        </div>

        <div class="flex items-center justify-between">
          <div class="flex flex-col gap-1">
            <h3 class="text-lg font-bold">{$t('settings.general.wrappedOnHome')}</h3>
            <p class="text-sm text-muma-spotify-text">{$t('settings.general.wrappedOnHomeHelp')}</p>
          </div>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" class="sr-only peer" checked={$wrappedOnHomeEnabled} onchange={toggleWrappedOnHome}>
            <div class="w-11 h-6 bg-muma-spotify-hover peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
          </label>
        </div>

        <div class="flex items-center justify-between">
          <div class="flex flex-col gap-1">
            <h3 class="text-lg font-bold">{$t('settings.general.pageSize')}</h3>
            <p class="text-sm text-muma-spotify-text">{$t('settings.general.pageSizeHelp')}</p>
          </div>
          <select
            class="bg-muma-spotify-hover border border-white/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
            aria-label={$t('settings.general.pageSize')}
            value={$trackPageSize}
            onchange={(e) => trackPageSize.set(Number(e.currentTarget.value))}
          >
            {#each TRACK_PAGE_SIZES as size (size)}
              <option value={size}>{size}</option>
            {/each}
          </select>
        </div>

        <div class="flex items-center justify-between">
          <div class="flex flex-col gap-1">
            <h3 class="text-lg font-bold">{$t('settings.general.albumSort')}</h3>
            <p class="text-sm text-muma-spotify-text">{$t('settings.general.albumSortHelp')}</p>
          </div>
          <select bind:value={settings.uiArtistReleaseSortMethod} aria-label={$t('settings.general.albumSort')} class="bg-muma-spotify-light text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand">
            <option value={2}>{$t('settings.general.sortByName')}</option>
            <option value={5}>{$t('settings.general.sortYearAsc')}</option>
            <option value={6}>{$t('settings.general.sortYearDesc')}</option>
            <option value={7}>{$t('settings.general.sortOriginalYearAsc')}</option>
            <option value={8}>{$t('settings.general.sortOriginalYearDesc')}</option>
          </select>
        </div>

        <div class="flex flex-col gap-4 mt-4 pt-4 border-t border-white/5">
            <div class="flex items-center justify-between">
                <div class="flex flex-col gap-1">
                    <h3 class="text-lg font-bold">{$t('settings.general.artistRelations')}</h3>
                    <p class="text-sm text-muma-spotify-text">{$t('settings.general.artistRelationsHelp')}</p>
                </div>
                <label class="relative inline-flex items-center cursor-pointer">
                    <input type="checkbox" class="sr-only peer" bind:checked={settings.uiEnableInlineArtistRelationships}>
                    <div class="w-11 h-6 bg-muma-spotify-hover peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
                </label>
            </div>

            {#if settings.uiEnableInlineArtistRelationships}
                <div class="flex flex-wrap gap-2 mt-2">
                    {#each artistRoles as role (role.id)}
                        <button
                            onclick={() => toggleRole(role.id)}
                            class="px-4 py-2 rounded-full text-xs font-bold transition-all {settings.uiInlineArtistRelationships.includes(role.id) ? 'bg-brand text-black' : 'bg-muma-spotify-light text-white hover:bg-muma-spotify-hover'}"
                        >
                            {$t(role.labelKey)}
                        </button>
                    {/each}
                </div>
            {/if}
        </div>
      </div>
    </section>

    <!-- Home Section -->
    <section class="bg-muma-spotify-panel rounded-lg p-6 shadow-lg border border-white/5">
      <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.general.home.title')}</h2>
      <p class="text-xs text-muma-spotify-text mb-6">{$t('settings.general.home.help')}</p>

      <div class="flex flex-col gap-6">
        <div class="flex items-center justify-between gap-4">
          <h3 class="text-lg font-bold">{$t('settings.general.home.releaseRadar')}</h3>
          <select
            class="bg-muma-spotify-light text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand"
            aria-label={$t('settings.general.home.releaseRadar')}
            value={$homeModeReleaseRadar}
            onchange={(e) => homeModeReleaseRadar.set(e.currentTarget.value)}
          >
            {#each HOME_MODE_OPTIONS as option (option.value)}
              <option value={option.value}>{$t(option.labelKey)}</option>
            {/each}
          </select>
        </div>

        <div class="flex items-center justify-between gap-4">
          <h3 class="text-lg font-bold">{$t('settings.general.home.dailyMix')}</h3>
          <select
            class="bg-muma-spotify-light text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand"
            aria-label={$t('settings.general.home.dailyMix')}
            value={$homeModeDailyMix}
            onchange={(e) => homeModeDailyMix.set(e.currentTarget.value)}
          >
            {#each HOME_MODE_OPTIONS as option (option.value)}
              <option value={option.value}>{$t(option.labelKey)}</option>
            {/each}
          </select>
        </div>

        <div class="flex items-center justify-between gap-4">
          <h3 class="text-lg font-bold">{$t('settings.general.home.favorites')}</h3>
          <select
            class="bg-muma-spotify-light text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand"
            aria-label={$t('settings.general.home.favorites')}
            value={$homeModeFavorites}
            onchange={(e) => homeModeFavorites.set(e.currentTarget.value)}
          >
            {#each HOME_MODE_OPTIONS as option (option.value)}
              <option value={option.value}>{$t(option.labelKey)}</option>
            {/each}
          </select>
        </div>

        <div class="flex items-center justify-between gap-4">
          <h3 class="text-lg font-bold">{$t('settings.general.home.shortcuts')}</h3>
          <select
            class="bg-muma-spotify-light text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand"
            aria-label={$t('settings.general.home.shortcuts')}
            value={$homeModeShortcuts}
            onchange={(e) => homeModeShortcuts.set(e.currentTarget.value)}
          >
            {#each HOME_MODE_OPTIONS as option (option.value)}
              <option value={option.value}>{$t(option.labelKey)}</option>
            {/each}
          </select>
        </div>

        <div class="flex items-center justify-between gap-4">
          <h3 class="text-lg font-bold">{$t('settings.general.home.recentlyReleased')}</h3>
          <select
            class="bg-muma-spotify-light text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand"
            aria-label={$t('settings.general.home.recentlyReleased')}
            value={$homeModeRecentlyReleased}
            onchange={(e) => homeModeRecentlyReleased.set(e.currentTarget.value)}
          >
            {#each HOME_MODE_OPTIONS as option (option.value)}
              <option value={option.value}>{$t(option.labelKey)}</option>
            {/each}
          </select>
        </div>

        <div class="flex items-center justify-between gap-4">
          <h3 class="text-lg font-bold">{$t('settings.general.home.recentlyAdded')}</h3>
          <select
            class="bg-muma-spotify-light text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand"
            aria-label={$t('settings.general.home.recentlyAdded')}
            value={$homeModeRecentlyAdded}
            onchange={(e) => homeModeRecentlyAdded.set(e.currentTarget.value)}
          >
            {#each HOME_MODE_OPTIONS as option (option.value)}
              <option value={option.value}>{$t(option.labelKey)}</option>
            {/each}
          </select>
        </div>

        <div class="flex items-center justify-between gap-4">
          <h3 class="text-lg font-bold">{$t('settings.general.home.dailyMixCount')}</h3>
          <select
            class="bg-muma-spotify-light text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand"
            aria-label={$t('settings.general.home.dailyMixCount')}
            value={$homeCountDailyMix}
            onchange={(e) => homeCountDailyMix.set(Number(e.currentTarget.value))}
          >
            {#each HOME_COUNT_STEPS as count (count)}
              <option value={count}>{count}</option>
            {/each}
          </select>
        </div>

        <div class="flex items-center justify-between gap-4">
          <h3 class="text-lg font-bold">{$t('settings.general.home.favoritesCount')}</h3>
          <select
            class="bg-muma-spotify-light text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand"
            aria-label={$t('settings.general.home.favoritesCount')}
            value={$homeCountFavorites}
            onchange={(e) => homeCountFavorites.set(Number(e.currentTarget.value))}
          >
            {#each HOME_COUNT_STEPS as count (count)}
              <option value={count}>{count}</option>
            {/each}
          </select>
        </div>

        <div class="flex items-center justify-between gap-4">
          <h3 class="text-lg font-bold">{$t('settings.general.home.shortcutCount')}</h3>
          <select
            class="bg-muma-spotify-light text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand"
            aria-label={$t('settings.general.home.shortcutCount')}
            value={$homeShortcutCount}
            onchange={(e) => homeShortcutCount.set(Number(e.currentTarget.value))}
          >
            {#each [4, 6, 8, 10, 12] as count (count)}
              <option value={count}>{count}</option>
            {/each}
          </select>
        </div>

        <div class="flex items-center justify-between gap-4">
          <h3 class="text-lg font-bold">{$t('settings.general.home.listCount')}</h3>
          <select
            class="bg-muma-spotify-light text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand"
            aria-label={$t('settings.general.home.listCount')}
            value={$homeListCount}
            onchange={(e) => homeListCount.set(Number(e.currentTarget.value))}
          >
            {#each [3, 5, 8, 10] as count (count)}
              <option value={count}>{count}</option>
            {/each}
          </select>
        </div>

        <div class="flex items-center justify-between">
          <div class="flex flex-col gap-1">
            <h3 class="text-lg font-bold">{$t('settings.general.home.separateHistory')}</h3>
            <p class="text-sm text-muma-spotify-text">{$t('settings.general.home.separateHistoryHelp')}</p>
          </div>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" class="sr-only peer" checked={$separateHomeHistory} onchange={() => separateHomeHistory.update((v) => !v)}>
            <div class="w-11 h-6 bg-muma-spotify-hover peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
          </label>
        </div>
      </div>
    </section>

    <!-- Weergave (display) Section -->
    <section class="bg-muma-spotify-panel rounded-lg p-6 shadow-lg border border-white/5">
      <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.general.display.title')}</h2>

      <div class="flex flex-col gap-6">
        <div class="flex items-center justify-between">
          <h3 class="text-lg font-bold">{$t('settings.general.display.showConfirmationDialog')}</h3>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" class="sr-only peer" checked={$showConfirmationDialog} onchange={() => showConfirmationDialog.update((v) => !v)}>
            <div class="w-11 h-6 bg-muma-spotify-hover peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
          </label>
        </div>

        <div class="flex items-center justify-between">
          <h3 class="text-lg font-bold">{$t('settings.general.display.showTrackNumber')}</h3>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" class="sr-only peer" checked={$showTrackNumber} onchange={() => showTrackNumber.update((v) => !v)}>
            <div class="w-11 h-6 bg-muma-spotify-hover peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
          </label>
        </div>

        <div class="flex items-center justify-between gap-4">
          <h3 class="text-lg font-bold">{$t('settings.general.display.trackListLines')}</h3>
          <select
            class="bg-muma-spotify-light text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand"
            aria-label={$t('settings.general.display.trackListLines')}
            value={$trackListLines}
            onchange={(e) => trackListLines.set(Number(e.currentTarget.value))}
          >
            {#each TRACK_LIST_LINES_OPTIONS as option (option.value)}
              <option value={option.value}>{$t(option.labelKey)}</option>
            {/each}
          </select>
        </div>

        <div class="flex items-center justify-between">
          <h3 class="text-lg font-bold">{$t('settings.general.display.displayBitrateWithArtist')}</h3>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" class="sr-only peer" checked={$displayBitrateWithArtist} onchange={() => displayBitrateWithArtist.update((v) => !v)}>
            <div class="w-11 h-6 bg-muma-spotify-hover peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
          </label>
        </div>

        <div class="flex items-center justify-between">
          <div class="flex flex-col gap-1">
            <h3 class="text-lg font-bold">{$t('settings.general.display.discSort')}</h3>
            <p class="text-sm text-muma-spotify-text">{$t('settings.general.display.discSortHelp')}</p>
          </div>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" class="sr-only peer" checked={$discSort} onchange={() => discSort.update((v) => !v)}>
            <div class="w-11 h-6 bg-muma-spotify-hover peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
          </label>
        </div>

        <div class="flex items-center justify-between gap-4">
          <div class="flex flex-col gap-1">
            <h3 class="text-lg font-bold">{$t('settings.general.display.genreTrackLimit')}</h3>
            <p class="text-sm text-muma-spotify-text">{$t('settings.general.display.genreTrackLimitHelp')}</p>
          </div>
          <select
            class="bg-muma-spotify-light text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand"
            aria-label={$t('settings.general.display.genreTrackLimit')}
            value={$genreTrackLimit}
            onchange={(e) => genreTrackLimit.set(Number(e.currentTarget.value))}
          >
            {#each [50, 100, 200, 500] as count (count)}
              <option value={count}>{count}</option>
            {/each}
          </select>
        </div>
      </div>
    </section>

    {#if downloadsSupported}
      <!-- Downloads Section -->
      <section class="bg-muma-spotify-panel rounded-lg p-6 shadow-lg border border-white/5">
        <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.general.downloads')}</h2>

        <div class="flex items-center justify-between">
          <div class="flex flex-col gap-1">
            <h3 class="text-lg font-bold">{$t('settings.general.wifiOnly')}</h3>
            <p class="text-sm text-muma-spotify-text">{$t('settings.general.wifiOnlyHelp')}</p>
          </div>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" class="sr-only peer" checked={nativeWifiOnly} onchange={toggleWifiOnly} aria-label={$t('settings.general.wifiOnly')}>
            <div class="w-11 h-6 bg-muma-spotify-hover peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
          </label>
        </div>
      </section>
    {/if}

    <!-- Subsonic Section -->
    <section class="bg-muma-spotify-panel rounded-lg p-6 shadow-lg border border-white/5">
      <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.general.externalClients')}</h2>

      <p class="text-xs text-muma-spotify-text mb-6">
        {$t('settings.general.apiKeyHelp')}
      </p>

      <div class="flex flex-col gap-6">
        <div class="grid grid-cols-2 gap-8">
            <div class="flex flex-col gap-2">
                <h3 class="font-bold">{$t('settings.general.artistListMode')}</h3>
                <p class="text-xs text-muma-spotify-text mb-2">{$t('settings.general.artistListModeHelp')}</p>
                <select bind:value={settings.subsonicArtistListMode} aria-label={$t('settings.general.artistListMode')} class="bg-muma-spotify-light text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand">
                    <option value={0}>{$t('settings.general.allArtists')}</option>
                    <option value={1}>{$t('settings.general.releaseArtists')}</option>
                    <option value={2}>{$t('settings.general.trackArtists')}</option>
                </select>
            </div>

            <div class="flex items-center justify-between">
                <div class="flex flex-col gap-1">
                    <h3 class="font-bold">{$t('settings.general.transcodingDefault')}</h3>
                    <p class="text-xs text-muma-spotify-text">{$t('settings.general.transcodingHelp')}</p>
                </div>
                <label class="relative inline-flex items-center cursor-pointer">
                    <input type="checkbox" class="sr-only peer" bind:checked={settings.subsonicEnableTranscodingByDefault}>
                    <div class="w-11 h-6 bg-muma-spotify-hover peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
                </label>
            </div>
        </div>

        <div class="grid grid-cols-2 gap-8">
            <div class="flex flex-col gap-2">
                <h3 class="font-bold">{$t('settings.general.subsonicFormat')}</h3>
                <select bind:value={settings.subsonicDefaultTranscodeFormat} aria-label={$t('settings.general.subsonicFormat')} class="bg-muma-spotify-light text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand">
                    <option value={1}>MP3</option>
                    <option value={2}>OGG Opus</option>
                    <option value={3}>OGG Vorbis</option>
                </select>
            </div>
            <div class="flex flex-col gap-2">
                <h3 class="font-bold">{$t('settings.general.subsonicBitrate')}</h3>
                <select bind:value={settings.subsonicDefaultTranscodeBitrate} aria-label={$t('settings.general.subsonicBitrate')} class="bg-muma-spotify-light text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand">
                    <option value={64000}>64 kbps</option>
                    <option value={96000}>96 kbps</option>
                    <option value={128000}>128 kbps</option>
                    <option value={192000}>192 kbps</option>
                    <option value={256000}>256 kbps</option>
                    <option value={320000}>320 kbps</option>
                </select>
            </div>
        </div>
      </div>
    </section>

    <!-- Services Section -->
    <section class="bg-muma-spotify-panel rounded-lg p-6 shadow-lg border border-white/5">
      <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.general.externalServices')}</h2>

      <div class="flex flex-col gap-6">
        <div class="flex flex-col gap-2">
          <h3 class="font-bold">{$t('settings.general.feedbackSystem')}</h3>
          <select bind:value={settings.feedbackBackend} aria-label={$t('settings.general.feedbackSystem')} class="bg-muma-spotify-light text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand">
            <option value={0}>{$t('settings.general.internal')}</option>
            <option value={1}>ListenBrainz</option>
            <option value={2}>Muma Rating Service</option>
          </select>
        </div>

        <div class="flex flex-col gap-2">
          <h3 class="font-bold">{$t('settings.general.listenBrainzToken')}</h3>
          <p class="text-xs text-muma-spotify-text mb-2">
            {$t('settings.general.listenBrainzHelp')}
          </p>
          <input
            type="password"
            bind:value={settings.listenbrainzToken}
            placeholder={$t('settings.general.listenBrainzPlaceholder')}
            class="bg-muma-spotify-light text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand w-full"
          />
        </div>
      </div>
    </section>
  </div>
</div>

<style>
  .bg-brand {
    background-color: #1ed760;
  }
  .text-brand {
    color: #1ed760;
  }
</style>
