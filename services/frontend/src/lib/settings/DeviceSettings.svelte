<script>
  import "./density.css";
  import { t } from '../i18n/index.js';
  import { onMount } from 'svelte';
  import { platform } from '../platform/index.js';
  import { logAction } from '../diagnosticsLog.js';
  import Modal from '../Modal.svelte';
  import FirstRunServer from '../FirstRunServer.svelte';
  import { useServerAddress, sameServer, switchServer } from '../serverAddress.js';

  /**
   * `null` while `getSettings()` has not resolved yet. Once it has, every field
   * `platform.system.getSettings()` answers with lives here, read and written
   * straight from this object -- see `writeSetting`.
   */
  let settings = $state(null);
  let isLoading = $state(true);
  let loadError = $state('');
  let saveError = $state('');

  let isClearingCache = $state(false);
  let cacheStatus = $state('');
  let diagnosticsStatus = $state('');

  const BLUETOOTH_OPTIONS = [
    { value: 0, labelKey: 'settings.device.bluetoothAll' },
    { value: 1, labelKey: 'settings.device.bluetoothA2dp' },
    { value: 2, labelKey: 'settings.device.bluetoothDisabled' }
  ];

  // Same steps the legacy settings screen offers (`arrays.xml`'s maxBitrateValues); 0 is
  // "no limit" on both sides, kept last to match that screen's order.
  const BITRATE_STEPS = [32, 64, 80, 96, 112, 128, 160, 192, 256, 320];

  // cacheSizeValues, in MB; -1 is "no limit".
  const CACHE_SIZE_STEPS_MB = [
    100, 200, 500, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000, 15000, 20000,
    25000, 30000, 100000, 250000
  ];

  // preloadCountValues; -1 is "the whole queue".
  const PRELOAD_STEPS = [1, 2, 3, 5, 10, 50, 100, 500, 1000, 10000, 100000];

  const PARALLEL_DOWNLOAD_STEPS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

  // networkTimeoutValues, milliseconds.
  const NETWORK_TIMEOUT_STEPS = [15000, 30000, 45000, 60000, 75000, 90000, 105000, 120000];

  // directoryCacheTimeValues, seconds; 0 is "don't cache directory listings".
  const DIRECTORY_CACHE_TIME_STEPS = [0, 60, 120, 300, 600, 1800, 3600];

  let bondedDevices = $state([]);
  let bondedPermissionGranted = $state(true);
  let selectedDeviceAddresses = $state([]);
  let isDevicePickerOpen = $state(false);
  let isLoadingDevices = $state(false);

  /** The server address in use, the first-run screen open to change it, and a checked other server waiting for a yes. */
  let serverAddress = $state(platform.system.serverUrl().subsonic);
  let isChangingServer = $state(false);
  let pendingServer = $state(null);
  let isSwitchingServer = $state(false);

  /**
   * The first-run screen checked an address. Another spelling of the same server is stored at
   * once and keeps the session; another server waits for the confirmation dialog (issue #192).
   *
   * @param {{url: string}} check
   */
  async function serverChecked(check) {
    if (sameServer(serverAddress, check.url)) {
      const urls = await useServerAddress(check.url, { signOut: false });
      serverAddress = urls.subsonic;
      isChangingServer = false;
      return;
    }
    pendingServer = check.url;
    isChangingServer = false;
  }

  /** The listener said yes: sign out, switch, and reload onto the new server's login page. */
  async function confirmServerSwitch() {
    if (!pendingServer || isSwitchingServer) return;
    isSwitchingServer = true;
    logAction('settings.server.switch');
    try {
      await switchServer(pendingServer);
      window.location.reload();
    } catch (e) {
      console.error('Could not switch to the other server', e);
      saveError = $t('firstRun.saveFailed', { reason: e?.message || e?.code || '?' });
      pendingServer = null;
      isSwitchingServer = false;
    }
  }

  onMount(async () => {
    try {
      settings = await platform.system.getSettings();
    } catch (e) {
      loadError = $t('settings.device.loadError');
      console.error('Failed to load the device settings', e);
    } finally {
      isLoading = false;
    }
  });

  /**
   * Writes one field optimistically, and rolls back if the native whitelist rejects it --
   * an unrecognised key or a value of the wrong type would otherwise leave the toggle showing
   * something that was never actually saved.
   *
   * @param {string} key
   * @param {boolean|number} value
   */
  async function writeSetting(key, value) {
    const previous = settings[key];
    settings = { ...settings, [key]: value };
    saveError = '';
    logAction('settings.set', { key, value });
    try {
      await platform.system.setSetting({ key, value });
    } catch (e) {
      settings = { ...settings, [key]: previous };
      saveError = $t('settings.device.saveError');
      console.error(`Failed to save the device setting "${key}"`, e);
    }
  }

  function toggle(key) {
    writeSetting(key, !settings[key]);
  }

  /** @param {string} key @param {Event} event */
  function writeFromSelect(key, event) {
    writeSetting(key, Number(event.currentTarget.value));
  }

  async function clearCache() {
    isClearingCache = true;
    cacheStatus = '';
    try {
      await platform.storage.clearCache();
      cacheStatus = $t('settings.device.cacheCleared');
    } catch (e) {
      cacheStatus = $t('settings.device.cacheClearError');
      console.error('Failed to clear the cache', e);
    } finally {
      isClearingCache = false;
    }
  }

  /** Fire-and-forget on the Kotlin side. */
  function sendDiagnostics() {
    platform.diagnostics.send();
    diagnosticsStatus = $t('settings.device.diagnosticsSent');
  }

  function requestCarModeFullScreenPermission() {
    platform.system.requestCarModeFullScreenPermission();
  }

  /**
   * Opens the car-mode device picker, pre-ticking whatever `carModeDevices` already holds -- or,
   * if nothing has been chosen yet, the devices that look like a car -- same as the legacy
   * screen's `preTickedCarDevices`.
   */
  async function openDevicePicker() {
    isDevicePickerOpen = true;
    isLoadingDevices = true;
    try {
      const answer = await platform.system.listBondedDevices();
      bondedPermissionGranted = answer.permissionGranted;
      bondedDevices = answer.devices;
      const stored = settings.carModeDevices;
      selectedDeviceAddresses =
        Array.isArray(stored) && stored.length > 0
          ? [...stored]
          : bondedDevices.filter((d) => d.isCarClass).map((d) => d.address);
    } catch (e) {
      bondedPermissionGranted = false;
      bondedDevices = [];
      console.error('Failed to list bonded Bluetooth devices', e);
    } finally {
      isLoadingDevices = false;
    }
  }

  function toggleDeviceSelected(address) {
    selectedDeviceAddresses = selectedDeviceAddresses.includes(address)
      ? selectedDeviceAddresses.filter((a) => a !== address)
      : [...selectedDeviceAddresses, address];
  }

  async function saveDeviceSelection() {
    await writeSetting('carModeDevices', selectedDeviceAddresses);
    isDevicePickerOpen = false;
  }

  /** @param {Event} event */
  async function pickCacheLocation() {
    saveError = '';
    try {
      const answer = await platform.system.pickCacheLocation();
      if (answer?.uri) {
        settings = { ...settings, cacheLocationUri: answer.path || answer.uri, customCacheLocation: true };
      }
    } catch (e) {
      saveError = $t('settings.device.saveError');
      console.error('Failed to pick a cache location', e);
    }
  }

  async function clearCustomCacheLocation() {
    saveError = '';
    try {
      await platform.system.clearCustomCacheLocation();
      settings = { ...settings, cacheLocationUri: '', customCacheLocation: false };
    } catch (e) {
      saveError = $t('settings.device.saveError');
      console.error('Failed to clear the custom cache location', e);
    }
  }
</script>

<div class="settings-density p-0 max-w-4xl mx-auto pb-24">
  <header class="mb-8">
    <h1 class="text-3xl font-bold mb-2">{$t('settings.device.title')}</h1>
    <p class="text-muma-spotify-text">{$t('settings.device.subtitle')}</p>
  </header>

  {#if isLoading}
    <p class="text-muma-spotify-text">{$t('settings.device.loading')}</p>
  {:else if !settings}
    <p class="text-red-400">{loadError}</p>
  {:else}
    {#if saveError}
      <div class="mb-6 p-4 rounded text-center font-medium bg-red-500/10 border border-red-500/20 text-red-400">
        {saveError}
      </div>
    {/if}

    <div class="flex flex-col gap-6">
      <!-- Server: the address the first-run screen stored (issue #192). -->
      <section class="bg-muma-spotify-panel rounded-lg p-6 shadow-lg border border-white/5" data-testid="device-server">
        <div class="flex items-center justify-between gap-4">
          <div class="flex flex-col gap-1 min-w-0">
            <h3 class="text-lg font-bold">{$t('settings.device.server')}</h3>
            <p class="text-sm text-muma-spotify-text break-all">{serverAddress || $t('settings.device.serverNone')}</p>
          </div>
          <button
            type="button"
            class="bg-muma-spotify-hover hover:bg-[#444] text-white font-bold py-2 px-6 rounded-full shrink-0"
            onclick={() => (isChangingServer = true)}
          >{$t('settings.device.serverChange')}</button>
        </div>
      </section>

      <!-- Downloads -->
      <section class="bg-muma-spotify-panel rounded-lg p-6 shadow-lg border border-white/5">
        <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.device.groups.downloads')}</h2>
        <div class="flex flex-col gap-6">
          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.wifiOnly')}</h3>
              <p class="text-sm text-muma-spotify-text">{$t('settings.device.wifiOnlyHelp')}</p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" class="sr-only peer" checked={settings.wifiOnly} onchange={() => toggle('wifiOnly')} aria-label={$t('settings.device.wifiOnly')}>
              <div class="w-11 h-6 bg-muma-spotify-hover peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
            </label>
          </div>

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.parallelDownloads')}</h3>
              <p class="text-sm text-muma-spotify-text">{$t('settings.device.parallelDownloadsHelp')}</p>
            </div>
            <select
              class="bg-muma-spotify-hover border border-white/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
              aria-label={$t('settings.device.parallelDownloads')}
              value={settings.parallelDownloads}
              onchange={(e) => writeFromSelect('parallelDownloads', e)}
            >
              {#each PARALLEL_DOWNLOAD_STEPS as count (count)}
                <option value={count}>{count}</option>
              {/each}
            </select>
          </div>

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.cacheSize')}</h3>
              <p class="text-sm text-muma-spotify-text">{$t('settings.device.cacheSizeHelp')}</p>
            </div>
            <select
              class="bg-muma-spotify-hover border border-white/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
              aria-label={$t('settings.device.cacheSize')}
              value={settings.cacheSizeMB}
              onchange={(e) => writeFromSelect('cacheSizeMB', e)}
            >
              {#each CACHE_SIZE_STEPS_MB as mb (mb)}
                <option value={mb}>{mb} MB</option>
              {/each}
              <option value={-1}>{$t('settings.device.cacheSizeUnlimited')}</option>
            </select>
          </div>

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.clearCache')}</h3>
              <p class="text-sm text-muma-spotify-text">
                {cacheStatus || $t('settings.device.clearCacheHelp')}
              </p>
            </div>
            <button
              onclick={clearCache}
              disabled={isClearingCache}
              class="bg-muma-spotify-hover hover:bg-[#444] text-white font-bold py-2 px-6 rounded-full transition-colors whitespace-nowrap shrink-0 disabled:opacity-50"
            >
              {isClearingCache ? $t('settings.device.clearingCache') : $t('settings.device.clearCache')}
            </button>
          </div>

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.cacheLocation')}</h3>
              <span class="text-sm text-muma-spotify-text">{settings.cacheLocationUri || $t('settings.device.cacheLocationDefault')}</span>
            </div>
            <div class="flex gap-2 shrink-0">
              {#if settings.customCacheLocation}
                <button onclick={clearCustomCacheLocation} class="bg-muma-spotify-hover hover:bg-[#444] text-white font-bold py-2 px-6 rounded-full transition-colors whitespace-nowrap">
                  {$t('settings.device.cacheLocationReset')}
                </button>
              {/if}
              <button onclick={pickCacheLocation} class="bg-muma-spotify-hover hover:bg-[#444] text-white font-bold py-2 px-6 rounded-full transition-colors whitespace-nowrap">
                {$t('settings.device.cacheLocationChoose')}
              </button>
            </div>
          </div>

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.directoryCacheTime')}</h3>
              <p class="text-sm text-muma-spotify-text">{$t('settings.device.directoryCacheTimeHelp')}</p>
            </div>
            <select
              class="bg-muma-spotify-hover border border-white/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
              aria-label={$t('settings.device.directoryCacheTime')}
              value={settings.directoryCacheTime}
              onchange={(e) => writeFromSelect('directoryCacheTime', e)}
            >
              {#each DIRECTORY_CACHE_TIME_STEPS as seconds (seconds)}
                <option value={seconds}>{seconds === 0 ? $t('settings.device.directoryCacheTimeOff') : `${Math.round(seconds / 60)} min`}</option>
              {/each}
            </select>
          </div>

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.mediaDeviceExport')}</h3>
              <p class="text-sm text-muma-spotify-text">{$t('settings.device.mediaDeviceExportHelp')}</p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" class="sr-only peer" checked={settings.mediaDeviceExport} onchange={() => toggle('mediaDeviceExport')} aria-label={$t('settings.device.mediaDeviceExport')}>
              <div class="w-11 h-6 bg-muma-spotify-hover peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
            </label>
          </div>
        </div>
      </section>

      <!-- Streaming -->
      <section class="bg-muma-spotify-panel rounded-lg p-6 shadow-lg border border-white/5">
        <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.device.groups.streaming')}</h2>
        <div class="flex flex-col gap-6">
          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.maxBitrateMobile')}</h3>
              <p class="text-sm text-muma-spotify-text">{$t('settings.device.maxBitrateMobileHelp')}</p>
            </div>
            <select
              class="bg-muma-spotify-hover border border-white/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
              aria-label={$t('settings.device.maxBitrateMobile')}
              value={settings.maxBitrateMobile}
              onchange={(e) => writeFromSelect('maxBitrateMobile', e)}
            >
              {#each BITRATE_STEPS as kbps (kbps)}
                <option value={kbps}>{kbps} kbps</option>
              {/each}
              <option value={0}>{$t('settings.device.bitrateUnlimited')}</option>
            </select>
          </div>

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.maxBitrateWifi')}</h3>
              <p class="text-sm text-muma-spotify-text">{$t('settings.device.maxBitrateWifiHelp')}</p>
            </div>
            <select
              class="bg-muma-spotify-hover border border-white/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
              aria-label={$t('settings.device.maxBitrateWifi')}
              value={settings.maxBitrateWifi}
              onchange={(e) => writeFromSelect('maxBitrateWifi', e)}
            >
              {#each BITRATE_STEPS as kbps (kbps)}
                <option value={kbps}>{kbps} kbps</option>
              {/each}
              <option value={0}>{$t('settings.device.bitrateUnlimited')}</option>
            </select>
          </div>

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.preloadCount')}</h3>
              <p class="text-sm text-muma-spotify-text">{$t('settings.device.preloadCountHelp')}</p>
            </div>
            <select
              class="bg-muma-spotify-hover border border-white/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
              aria-label={$t('settings.device.preloadCount')}
              value={settings.preloadCount}
              onchange={(e) => writeFromSelect('preloadCount', e)}
            >
              {#each PRELOAD_STEPS as count (count)}
                <option value={count}>{count}</option>
              {/each}
              <option value={-1}>{$t('settings.device.preloadCountUnlimited')}</option>
            </select>
          </div>

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.maxBitratePinning')}</h3>
              <p class="text-sm text-muma-spotify-text">{$t('settings.device.maxBitratePinningHelp')}</p>
            </div>
            <select
              class="bg-muma-spotify-hover border border-white/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
              aria-label={$t('settings.device.maxBitratePinning')}
              value={settings.maxBitratePinning}
              onchange={(e) => writeFromSelect('maxBitratePinning', e)}
            >
              {#each BITRATE_STEPS as kbps (kbps)}
                <option value={kbps}>{kbps} kbps</option>
              {/each}
              <option value={0}>{$t('settings.device.bitrateHighestQuality')}</option>
            </select>
          </div>

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.networkTimeout')}</h3>
              <p class="text-sm text-muma-spotify-text">{$t('settings.device.networkTimeoutHelp')}</p>
            </div>
            <select
              class="bg-muma-spotify-hover border border-white/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
              aria-label={$t('settings.device.networkTimeout')}
              value={settings.networkTimeout}
              onchange={(e) => writeFromSelect('networkTimeout', e)}
            >
              {#each NETWORK_TIMEOUT_STEPS as ms (ms)}
                <option value={ms}>{ms / 1000}s</option>
              {/each}
            </select>
          </div>

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.autoSwitchOffline')}</h3>
              <p class="text-sm text-muma-spotify-text">{$t('settings.device.autoSwitchOfflineHelp')}</p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" class="sr-only peer" checked={settings.autoSwitchOffline} onchange={() => toggle('autoSwitchOffline')} aria-label={$t('settings.device.autoSwitchOffline')}>
              <div class="w-11 h-6 bg-muma-spotify-hover peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
            </label>
          </div>
        </div>
      </section>

      <!-- Playback -->
      <section class="bg-muma-spotify-panel rounded-lg p-6 shadow-lg border border-white/5">
        <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.device.groups.playback')}</h2>
        <div class="flex flex-col gap-6">
          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.resumeOnHeadphonesPlug')}</h3>
              <p class="text-sm text-muma-spotify-text">{$t('settings.device.resumeOnHeadphonesPlugHelp')}</p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" class="sr-only peer" checked={settings.resumeOnHeadphonesPlug} onchange={() => toggle('resumeOnHeadphonesPlug')} aria-label={$t('settings.device.resumeOnHeadphonesPlug')}>
              <div class="w-11 h-6 bg-muma-spotify-hover peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
            </label>
          </div>

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.resumeOnBluetoothDevice')}</h3>
              <p class="text-sm text-muma-spotify-text">{$t('settings.device.resumeOnBluetoothDeviceHelp')}</p>
            </div>
            <select
              class="bg-muma-spotify-hover border border-white/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
              aria-label={$t('settings.device.resumeOnBluetoothDevice')}
              value={settings.resumeOnBluetoothDevice}
              onchange={(e) => writeFromSelect('resumeOnBluetoothDevice', e)}
            >
              {#each BLUETOOTH_OPTIONS as option (option.value)}
                <option value={option.value}>{$t(option.labelKey)}</option>
              {/each}
            </select>
          </div>

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.pauseOnBluetoothDevice')}</h3>
              <p class="text-sm text-muma-spotify-text">{$t('settings.device.pauseOnBluetoothDeviceHelp')}</p>
            </div>
            <select
              class="bg-muma-spotify-hover border border-white/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
              aria-label={$t('settings.device.pauseOnBluetoothDevice')}
              value={settings.pauseOnBluetoothDevice}
              onchange={(e) => writeFromSelect('pauseOnBluetoothDevice', e)}
            >
              {#each BLUETOOTH_OPTIONS as option (option.value)}
                <option value={option.value}>{$t(option.labelKey)}</option>
              {/each}
            </select>
          </div>

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.hardwareOffload')}</h3>
              <p class="text-sm text-muma-spotify-text">{$t('settings.device.hardwareOffloadHelp')}</p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" class="sr-only peer" checked={settings.hardwareOffload} onchange={() => toggle('hardwareOffload')} aria-label={$t('settings.device.hardwareOffload')}>
              <div class="w-11 h-6 bg-muma-spotify-hover peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
            </label>
          </div>
        </div>
      </section>

      <!-- Car -->
      <section class="bg-muma-spotify-panel rounded-lg p-6 shadow-lg border border-white/5">
        <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.device.groups.car')}</h2>
        <div class="flex flex-col gap-6">
          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.carModeManual')}</h3>
              <p class="text-sm text-muma-spotify-text">{$t('settings.device.carModeManualHelp')}</p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" class="sr-only peer" checked={settings.carModeManual} onchange={() => toggle('carModeManual')} aria-label={$t('settings.device.carModeManual')}>
              <div class="w-11 h-6 bg-muma-spotify-hover peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
            </label>
          </div>

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.carModeDevices')}</h3>
              <p class="text-sm text-muma-spotify-text">
                {settings.carModeDevices?.length > 0
                  ? $t('settings.device.carModeDevicesCount', { count: settings.carModeDevices.length })
                  : $t('settings.device.carModeDevicesNone')}
              </p>
            </div>
            <button onclick={openDevicePicker} class="bg-muma-spotify-hover hover:bg-[#444] text-white font-bold py-2 px-6 rounded-full transition-colors whitespace-nowrap shrink-0">
              {$t('settings.device.carModeDevicesEdit')}
            </button>
          </div>

          {#if settings.carModeFullScreenGranted !== undefined}
            <div class="flex items-center justify-between gap-4">
              <div class="flex flex-col gap-1">
                <h3 class="text-lg font-bold">{$t('settings.device.carModeFullScreen')}</h3>
                <p class="text-sm text-muma-spotify-text">
                  {settings.carModeFullScreenGranted
                    ? $t('settings.device.carModeFullScreenGranted')
                    : $t('settings.device.carModeFullScreenDenied')}
                </p>
              </div>
              {#if !settings.carModeFullScreenGranted}
                <button onclick={requestCarModeFullScreenPermission} class="bg-muma-spotify-hover hover:bg-[#444] text-white font-bold py-2 px-6 rounded-full transition-colors whitespace-nowrap shrink-0">
                  {$t('settings.device.carModeFullScreenAction')}
                </button>
              {/if}
            </div>
          {/if}
        </div>
      </section>

      <!-- Diagnostics -->
      <section class="bg-muma-spotify-panel rounded-lg p-6 shadow-lg border border-white/5">
        <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.device.groups.diagnostics')}</h2>
        <div class="flex flex-col gap-6">
          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.sendDiagnostics')}</h3>
              <p class="text-sm text-muma-spotify-text">
                {diagnosticsStatus || $t('settings.device.sendDiagnosticsHelp')}
              </p>
            </div>
            <button onclick={sendDiagnostics} class="bg-muma-spotify-hover hover:bg-[#444] text-white font-bold py-2 px-6 rounded-full transition-colors whitespace-nowrap shrink-0">
              {$t('settings.device.sendDiagnostics')}
            </button>
          </div>

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.scrobbleEnabled')}</h3>
              <p class="text-sm text-muma-spotify-text">{$t('settings.device.scrobbleEnabledHelp')}</p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" class="sr-only peer" checked={settings.scrobbleEnabled} onchange={() => toggle('scrobbleEnabled')} aria-label={$t('settings.device.scrobbleEnabled')}>
              <div class="w-11 h-6 bg-muma-spotify-hover peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
            </label>
          </div>
        </div>
      </section>


      <!-- Other -->
      <section class="bg-muma-spotify-panel rounded-lg p-6 shadow-lg border border-white/5">
        <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.device.groups.other')}</h2>
        <div class="flex flex-col gap-6">
          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.hideMedia')}</h3>
              <p class="text-sm text-muma-spotify-text">{$t('settings.device.hideMediaHelp')}</p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" class="sr-only peer" checked={settings.hideMedia} onchange={() => toggle('hideMedia')} aria-label={$t('settings.device.hideMedia')}>
              <div class="w-11 h-6 bg-muma-spotify-hover peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
            </label>
          </div>
        </div>
      </section>

      <!-- Muma sync: read-only, filled by login -->
      <section class="bg-muma-spotify-panel rounded-lg p-6 shadow-lg border border-white/5">
        <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.device.groups.mumaSync')}</h2>
        <div class="flex flex-col gap-6">
          <div class="flex items-center justify-between gap-4">
            <h3 class="text-lg font-bold">{$t('settings.device.mumaUserId')}</h3>
            <span class="text-sm text-muma-spotify-text">{settings.mumaUserId ?? $t('settings.device.mumaSyncNotLinked')}</span>
          </div>
          <div class="flex items-center justify-between gap-4">
            <h3 class="text-lg font-bold">{$t('settings.device.mumaApiKeySet')}</h3>
            <span class="text-sm text-muma-spotify-text">
              {settings.mumaApiKeySet ? $t('settings.device.mumaSyncLinked') : $t('settings.device.mumaSyncNotLinked')}
            </span>
          </div>
        </div>
      </section>
    </div>

    {#if isChangingServer}
      <div class="fixed inset-0 z-[90] overflow-y-auto bg-black">
        <FirstRunServer
          mode="change"
          current={serverAddress}
          onconfirm={serverChecked}
          oncancel={() => (isChangingServer = false)}
        />
      </div>
    {/if}

    {#if pendingServer}
      <Modal title={$t('settings.device.serverSwitchTitle')} onclose={() => (pendingServer = null)} widthClass="max-w-md">
        <div class="flex flex-col gap-4" data-testid="server-switch-confirm">
          <p class="text-sm text-white m-0 break-all">{pendingServer}</p>
          <p class="text-sm text-muma-spotify-text m-0">{$t('settings.device.serverSwitchBody')}</p>
          <div class="flex flex-wrap gap-3 justify-end">
            <button
              class="bg-transparent border border-muma-spotify-muted text-white px-6 py-2 rounded-[24px] font-bold cursor-pointer hover:border-white"
              onclick={() => (pendingServer = null)}
              disabled={isSwitchingServer}
            >{$t('common.cancel')}</button>
            <button
              class="bg-brand text-black px-6 py-2 rounded-[24px] font-bold cursor-pointer disabled:opacity-50"
              data-testid="server-switch-confirm-button"
              onclick={confirmServerSwitch}
              disabled={isSwitchingServer}
            >{$t('settings.device.serverSwitchConfirm')}</button>
          </div>
        </div>
      </Modal>
    {/if}

    {#if isDevicePickerOpen}
      <Modal title={$t('settings.device.carModeDevicesEdit')} onclose={() => (isDevicePickerOpen = false)}>
        {#if isLoadingDevices}
          <p class="text-muma-spotify-text">{$t('settings.device.loading')}</p>
        {:else if !bondedPermissionGranted}
          <p class="text-muma-spotify-text">{$t('settings.device.bluetoothPermissionDenied')}</p>
        {:else if bondedDevices.length === 0}
          <p class="text-muma-spotify-text">{$t('settings.device.carModeDevicesNone')}</p>
        {:else}
          <div class="flex flex-col gap-3 mb-6">
            {#each bondedDevices as device (device.address)}
              <label class="flex items-center gap-3 p-3 bg-muma-spotify-light rounded-md cursor-pointer">
                <input
                  type="checkbox"
                  class="w-5 h-5 accent-brand"
                  checked={selectedDeviceAddresses.includes(device.address)}
                  onchange={() => toggleDeviceSelected(device.address)}
                />
                <span class="text-white font-medium">{device.name}</span>
              </label>
            {/each}
          </div>
          <button
            onclick={saveDeviceSelection}
            class="bg-brand text-black font-bold py-3 px-8 rounded-full hover:scale-105 transition-transform w-full"
          >
            {$t('common.saveChanges')}
          </button>
        {/if}
      </Modal>
    {/if}
  {/if}
</div>
