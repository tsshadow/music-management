<script>
  import { t } from '../i18n/index.js';
  import { onMount } from 'svelte';
  import { platform } from '../platform/index.js';

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

  /** Fire-and-forget on the Kotlin side, same as `switchToLegacyUi`/`openLegacySettings` below. */
  function sendDiagnostics() {
    platform.diagnostics.send();
    diagnosticsStatus = $t('settings.device.diagnosticsSent');
  }

  function switchToLegacyUi() {
    platform.system.switchToLegacyUi();
  }

  function openLegacySettings() {
    platform.system.openLegacySettings();
  }
</script>

<div class="p-8 max-w-4xl mx-auto pb-24">
  <header class="mb-8">
    <h1 class="text-3xl font-bold mb-2">{$t('settings.device.title')}</h1>
    <p class="text-[#b3b3b3]">{$t('settings.device.subtitle')}</p>
  </header>

  {#if isLoading}
    <p class="text-[#b3b3b3]">{$t('settings.device.loading')}</p>
  {:else if !settings}
    <p class="text-red-400">{loadError}</p>
  {:else}
    {#if saveError}
      <div class="mb-6 p-4 rounded text-center font-medium bg-red-500/10 border border-red-500/20 text-red-400">
        {saveError}
      </div>
    {/if}

    <div class="flex flex-col gap-6">
      <!-- Downloads -->
      <section class="bg-[#181818] rounded-lg p-6 shadow-lg border border-white/5">
        <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.device.groups.downloads')}</h2>
        <div class="flex flex-col gap-6">
          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.wifiOnly')}</h3>
              <p class="text-sm text-[#b3b3b3]">{$t('settings.device.wifiOnlyHelp')}</p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" class="sr-only peer" checked={settings.wifiOnly} onchange={() => toggle('wifiOnly')} aria-label={$t('settings.device.wifiOnly')}>
              <div class="w-11 h-6 bg-[#333] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
            </label>
          </div>

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.parallelDownloads')}</h3>
              <p class="text-sm text-[#b3b3b3]">{$t('settings.device.parallelDownloadsHelp')}</p>
            </div>
            <select
              class="bg-[#333] border border-white/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
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
              <p class="text-sm text-[#b3b3b3]">{$t('settings.device.cacheSizeHelp')}</p>
            </div>
            <select
              class="bg-[#333] border border-white/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
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
              <p class="text-sm text-[#b3b3b3]">
                {cacheStatus || $t('settings.device.clearCacheHelp')}
              </p>
            </div>
            <button
              onclick={clearCache}
              disabled={isClearingCache}
              class="bg-[#333] hover:bg-[#444] text-white font-bold py-2 px-6 rounded-full transition-colors whitespace-nowrap shrink-0 disabled:opacity-50"
            >
              {isClearingCache ? $t('settings.device.clearingCache') : $t('settings.device.clearCache')}
            </button>
          </div>

          <div class="flex items-center justify-between gap-4">
            <h3 class="text-lg font-bold">{$t('settings.device.cacheLocation')}</h3>
            <span class="text-sm text-[#b3b3b3]">{settings.cacheLocationUri || $t('settings.device.cacheLocationDefault')}</span>
          </div>
        </div>
      </section>

      <!-- Streaming -->
      <section class="bg-[#181818] rounded-lg p-6 shadow-lg border border-white/5">
        <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.device.groups.streaming')}</h2>
        <div class="flex flex-col gap-6">
          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.maxBitrateMobile')}</h3>
              <p class="text-sm text-[#b3b3b3]">{$t('settings.device.maxBitrateMobileHelp')}</p>
            </div>
            <select
              class="bg-[#333] border border-white/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
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
              <p class="text-sm text-[#b3b3b3]">{$t('settings.device.maxBitrateWifiHelp')}</p>
            </div>
            <select
              class="bg-[#333] border border-white/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
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
              <p class="text-sm text-[#b3b3b3]">{$t('settings.device.preloadCountHelp')}</p>
            </div>
            <select
              class="bg-[#333] border border-white/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
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
        </div>
      </section>

      <!-- Playback -->
      <section class="bg-[#181818] rounded-lg p-6 shadow-lg border border-white/5">
        <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.device.groups.playback')}</h2>
        <div class="flex flex-col gap-6">
          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.resumeOnHeadphonesPlug')}</h3>
              <p class="text-sm text-[#b3b3b3]">{$t('settings.device.resumeOnHeadphonesPlugHelp')}</p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" class="sr-only peer" checked={settings.resumeOnHeadphonesPlug} onchange={() => toggle('resumeOnHeadphonesPlug')} aria-label={$t('settings.device.resumeOnHeadphonesPlug')}>
              <div class="w-11 h-6 bg-[#333] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
            </label>
          </div>

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.resumeOnBluetoothDevice')}</h3>
              <p class="text-sm text-[#b3b3b3]">{$t('settings.device.resumeOnBluetoothDeviceHelp')}</p>
            </div>
            <select
              class="bg-[#333] border border-white/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
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
              <p class="text-sm text-[#b3b3b3]">{$t('settings.device.pauseOnBluetoothDeviceHelp')}</p>
            </div>
            <select
              class="bg-[#333] border border-white/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
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
              <p class="text-sm text-[#b3b3b3]">{$t('settings.device.hardwareOffloadHelp')}</p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" class="sr-only peer" checked={settings.hardwareOffload} onchange={() => toggle('hardwareOffload')} aria-label={$t('settings.device.hardwareOffload')}>
              <div class="w-11 h-6 bg-[#333] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
            </label>
          </div>
        </div>
      </section>

      <!-- Car -->
      <section class="bg-[#181818] rounded-lg p-6 shadow-lg border border-white/5">
        <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.device.groups.car')}</h2>
        <div class="flex flex-col gap-6">
          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.carModeManual')}</h3>
              <p class="text-sm text-[#b3b3b3]">{$t('settings.device.carModeManualHelp')}</p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" class="sr-only peer" checked={settings.carModeManual} onchange={() => toggle('carModeManual')} aria-label={$t('settings.device.carModeManual')}>
              <div class="w-11 h-6 bg-[#333] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
            </label>
          </div>

          <!-- Shown, not edited: pairing a device is a Bluetooth picker the legacy
               screen already has, and duplicating it here is not worth the seam. -->
          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.carModeDevices')}</h3>
              <p class="text-sm text-[#b3b3b3]">
                {settings.carModeDeviceCount > 0
                  ? $t('settings.device.carModeDevicesCount', { count: settings.carModeDeviceCount })
                  : $t('settings.device.carModeDevicesNone')}
              </p>
            </div>
            <button onclick={openLegacySettings} class="bg-[#333] hover:bg-[#444] text-white font-bold py-2 px-6 rounded-full transition-colors whitespace-nowrap shrink-0">
              {$t('settings.device.carModeDevicesEdit')}
            </button>
          </div>

          {#if settings.carModeFullScreenGranted !== undefined}
            <div class="flex items-center justify-between gap-4">
              <div class="flex flex-col gap-1">
                <h3 class="text-lg font-bold">{$t('settings.device.carModeFullScreen')}</h3>
                <p class="text-sm text-[#b3b3b3]">
                  {settings.carModeFullScreenGranted
                    ? $t('settings.device.carModeFullScreenGranted')
                    : $t('settings.device.carModeFullScreenDenied')}
                </p>
              </div>
              {#if !settings.carModeFullScreenGranted}
                <button onclick={openLegacySettings} class="bg-[#333] hover:bg-[#444] text-white font-bold py-2 px-6 rounded-full transition-colors whitespace-nowrap shrink-0">
                  {$t('settings.device.carModeFullScreenAction')}
                </button>
              {/if}
            </div>
          {/if}
        </div>
      </section>

      <!-- Diagnostics -->
      <section class="bg-[#181818] rounded-lg p-6 shadow-lg border border-white/5">
        <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.device.groups.diagnostics')}</h2>
        <div class="flex flex-col gap-6">
          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.sendDiagnostics')}</h3>
              <p class="text-sm text-[#b3b3b3]">
                {diagnosticsStatus || $t('settings.device.sendDiagnosticsHelp')}
              </p>
            </div>
            <button onclick={sendDiagnostics} class="bg-[#333] hover:bg-[#444] text-white font-bold py-2 px-6 rounded-full transition-colors whitespace-nowrap shrink-0">
              {$t('settings.device.sendDiagnostics')}
            </button>
          </div>

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.scrobbleEnabled')}</h3>
              <p class="text-sm text-[#b3b3b3]">{$t('settings.device.scrobbleEnabledHelp')}</p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" class="sr-only peer" checked={settings.scrobbleEnabled} onchange={() => toggle('scrobbleEnabled')} aria-label={$t('settings.device.scrobbleEnabled')}>
              <div class="w-11 h-6 bg-[#333] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
            </label>
          </div>
        </div>
      </section>

      <!-- Interface -->
      <section class="bg-[#181818] rounded-lg p-6 shadow-lg border border-white/5">
        <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.device.groups.interface')}</h2>
        <div class="flex flex-col gap-6">
          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.switchToLegacyUi')}</h3>
              <p class="text-sm text-[#b3b3b3]">{$t('settings.device.switchToLegacyUiHelp')}</p>
            </div>
            <button onclick={switchToLegacyUi} class="bg-[#333] hover:bg-[#444] text-white font-bold py-2 px-6 rounded-full transition-colors whitespace-nowrap shrink-0">
              {$t('settings.device.switchToLegacyUi')}
            </button>
          </div>

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">{$t('settings.device.allAppSettings')}</h3>
              <p class="text-sm text-[#b3b3b3]">{$t('settings.device.allAppSettingsHelp')}</p>
            </div>
            <button onclick={openLegacySettings} class="bg-[#333] hover:bg-[#444] text-white font-bold py-2 px-6 rounded-full transition-colors whitespace-nowrap shrink-0">
              {$t('settings.device.allAppSettings')}
            </button>
          </div>
        </div>
      </section>
    </div>
  {/if}
</div>
