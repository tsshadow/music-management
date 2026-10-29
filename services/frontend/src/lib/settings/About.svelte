<script>
  import "./density.css";
  import { t } from '../i18n/index.js';
  import { onMount } from 'svelte';
  import { authParams, restUrl } from '../store.js';
  import { platform as defaultPlatform } from '../platform/index.js';
  import { apiBase, fetchMumaJson } from '../mumaApi.js';
  import { fetchBundleVersion } from '../diagnosticsLog.js';
  import { parseMobileChangelog } from '../mobileReleaseNotes.js';
  import { checkForAppUpdate, isOtherSeries } from '../appUpdate.js';

  /**
   * The version overview. Four things run here and ship on four schedules -- the APK, the web
   * bundle inside it, the MuMa API and the LMS server -- and "which version are you on" is the
   * first question behind every bug report, so every one of them is listed rather than only the
   * LMS version this page used to show.
   *
   * The App block and the app's own release notes exist only inside the shell
   * (`platform.system.isNative`): a browser tab has no APK to describe or to update, and reads
   * the LMS server's `release-notes.json` as before.
   */
  const { platform = defaultPlatform } = $props();

  const isNative = $derived(platform?.system?.isNative === true);

  /** @type {import('../platform/index.js').AppInfo|null} */
  let appInfo = $state(null);
  let lmsVersion = $state('');
  let mumaVersion = $state('');
  let serverUrl = $state('');
  /** Where the source code lives (AGPL-3.0 section 13); empty hides the link. */
  let sourceUrl = $state('');
  /** @type {{version: string, builtAt: string|null}|null} */
  let bundle = $state(null);
  let isLoading = $state(true);
  let releaseNotes = $state([]);

  let checking = $state(false);
  /** What the last manual check found: 'available' | 'upToDate' | 'failed' | null. */
  let checkOutcome = $state(null);
  let latestVersion = $state('');

  /**
   * Every version this page lists, fetched side by side; one that fails leaves its row on
   * "onbekend" rather than taking the others down with it.
   */
  async function loadInfo() {
    const bases = platform.system.serverUrl();
    serverUrl = bases.subsonic || (typeof window === 'undefined' ? '' : window.location.origin);

    await Promise.all([
      loadAppInfo(),
      loadLmsVersion(),
      loadMumaVersion(),
      fetchBundleVersion().then((answer) => { bundle = answer; }),
      loadReleaseNotes(),
    ]);
    isLoading = false;
  }

  async function loadAppInfo() {
    if (!isNative) return;
    try {
      appInfo = await platform.system.appInfo();
    } catch (e) {
      console.warn('Could not read the app version', e);
    }
  }

  async function loadLmsVersion() {
    try {
      const response = await fetch(restUrl(`/rest/ping?${$authParams}`));
      const data = await response.json();
      const res = data['subsonic-response'];
      if (res) lmsVersion = res.serverVersion || res.version || '';
    } catch (e) {
      console.warn('Could not read the LMS version', e);
    }
  }

  async function loadMumaVersion() {
    try {
      const health = await fetchMumaJson(`${apiBase()}/health`);
      if (typeof health?.version === 'string') mumaVersion = health.version;
      if (typeof health?.source_url === 'string') sourceUrl = health.source_url;
    } catch (e) {
      // An unhealthy MuMa answers /health with 503 and the full report, version included.
      if (typeof e?.body?.version === 'string') mumaVersion = e.body.version;
      if (typeof e?.body?.source_url === 'string') sourceUrl = e.body.source_url;
      console.warn('Could not read the MuMa API version', e);
    }
  }

  /**
   * The app's own changelog on the phone -- the same parse `mobileReleaseNotes.js` runs for the
   * once-per-upgrade modal -- and the LMS server's notes in a browser, where there is no app.
   */
  async function loadReleaseNotes() {
    try {
      if (isNative) {
        const text = await platform.system.releaseNotes();
        releaseNotes = text ? parseMobileChangelog(text) : [];
        return;
      }
      const rnResponse = await fetch('/release-notes.json');
      if (rnResponse.ok) releaseNotes = await rnResponse.json();
    } catch (e) {
      console.warn('Could not read the release notes', e);
    }
  }

  /**
   * The button. `checkForAppUpdate` already toasts every outcome; the line under the button
   * repeats it so the answer stays on screen after the toast is gone.
   */
  async function checkNow() {
    checking = true;
    checkOutcome = null;
    try {
      const update = await checkForAppUpdate({ manual: true, platform });
      if (!update) {
        checkOutcome = 'failed';
      } else if (update.available) {
        // A release that outran this debug build is another package, not an update to this one.
        checkOutcome = isOtherSeries(update) ? 'releaseAhead' : 'available';
        latestVersion = update.latestVersionName;
      } else {
        checkOutcome = 'upToDate';
      }
    } finally {
      checking = false;
    }
  }

  /**
   * Opens the source link. In the app it goes to the system browser, as every other external
   * link does, instead of navigating the WebView away from the player.
   * @param {MouseEvent} event
   */
  function openSource(event) {
    if (!isNative) return;
    event.preventDefault();
    platform.system.openUrl(sourceUrl).catch((e) => console.warn('Could not open the source code link', e));
  }

  /**
   * @param {string|null} iso
   * @returns {string}
   */
  function builtAtLabel(iso) {
    if (!iso) return '';
    const date = new Date(iso);
    return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
  }

  onMount(loadInfo);
</script>

<div class="settings-density max-w-4xl pb-24">
  <header class="mb-8">
    <h1 class="text-3xl font-bold mb-2">{$t('settings.about.title')}</h1>
    <p class="text-muma-spotify-text">{$t('settings.about.subtitle')}</p>
  </header>

  <div class="flex flex-col gap-8">
    <section class="bg-muma-spotify-panel rounded-lg p-6 shadow-lg border border-white/5">
      <div class="flex items-center gap-6">
        <img
          src="/images/logo.svg"
          alt=""
          class="w-20 h-20"
          onerror={(e) => (e.currentTarget.src = '/images/spotify-fallback.svg')}
        />
        <div>
          <h2 class="text-white text-2xl font-bold">MuMa</h2>
          <p class="text-muma-spotify-text">
            {#if isLoading}
              {$t('common.loading')}
            {:else if isNative && appInfo}
              {$t('settings.about.appVersion')} {appInfo.version} ({appInfo.versionCode})
            {:else if mumaVersion || lmsVersion}
              {$t('settings.about.appVersion')} {mumaVersion || lmsVersion}
            {:else}
              {$t('settings.about.appVersion')} {$t('settings.about.unknown')}
            {/if}
          </p>
        </div>
      </div>
      <p class="text-muma-spotify-text text-sm mt-6">
        {$t('settings.about.blurb')}
      </p>
    </section>

    {#if isNative}
      <section class="bg-muma-spotify-panel rounded-lg p-6 shadow-lg border border-white/5" data-testid="about-app">
        <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.about.app')}</h2>
        <dl class="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
          <dt class="text-muma-spotify-text">{$t('settings.about.appVersion')}</dt>
          <dd class="text-white m-0">{appInfo ? `${appInfo.version} (${appInfo.versionCode})` : $t('settings.about.unknown')}</dd>
          <dt class="text-muma-spotify-text">{$t('settings.about.buildType')}</dt>
          <dd class="text-white m-0">{appInfo?.buildType || $t('settings.about.unknown')}</dd>
          <dt class="text-muma-spotify-text">{$t('settings.about.packageName')}</dt>
          <dd class="text-white m-0 break-all">{appInfo?.packageName || $t('settings.about.unknown')}</dd>
          <dt class="text-muma-spotify-text">{$t('settings.about.android')}</dt>
          <dd class="text-white m-0">{appInfo?.androidVersion || $t('settings.about.unknown')}</dd>
          <dt class="text-muma-spotify-text">{$t('settings.about.device')}</dt>
          <dd class="text-white m-0">{appInfo?.device || $t('settings.about.unknown')}</dd>
        </dl>
        <div class="mt-6 flex flex-col gap-2">
          <button
            type="button"
            class="self-start bg-white text-black font-bold text-sm px-5 py-2 rounded-full border-none cursor-pointer hover:scale-105 transition-transform disabled:opacity-60 disabled:cursor-wait"
            disabled={checking}
            onclick={checkNow}
          >
            {checking ? $t('settings.about.checking') : $t('settings.about.checkForUpdate')}
          </button>
          {#if checkOutcome === 'available'}
            <p class="text-sm text-brand m-0" data-testid="update-outcome">{$t('settings.about.updateAvailable', { version: latestVersion })}</p>
          {:else if checkOutcome === 'releaseAhead'}
            <p class="text-sm text-brand m-0" data-testid="update-outcome">{$t('appUpdate.releaseAhead', { version: latestVersion, current: appInfo?.version ?? '' })}</p>
          {:else if checkOutcome === 'upToDate'}
            <p class="text-sm text-muma-spotify-text m-0" data-testid="update-outcome">{$t('settings.about.upToDate')}</p>
          {:else if checkOutcome === 'failed'}
            <p class="text-sm text-red-400 m-0" data-testid="update-outcome">{$t('settings.about.checkFailed')}</p>
          {/if}
        </div>
      </section>
    {/if}

    <section class="bg-muma-spotify-panel rounded-lg p-6 shadow-lg border border-white/5" data-testid="about-server">
      <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.about.server')}</h2>
      <dl class="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
        <dt class="text-muma-spotify-text">{$t('settings.about.serverUrl')}</dt>
        <dd class="text-white m-0 break-all">{serverUrl || $t('settings.about.unknown')}</dd>
        <dt class="text-muma-spotify-text">{$t('settings.about.mumaVersion')}</dt>
        <dd class="text-white m-0">{mumaVersion || $t('settings.about.unknown')}</dd>
        <dt class="text-muma-spotify-text">{$t('settings.about.lmsVersion')}</dt>
        <dd class="text-white m-0">{lmsVersion || $t('settings.about.unknown')}</dd>
        <dt class="text-muma-spotify-text">{$t('settings.about.bundleVersion')}</dt>
        <dd class="text-white m-0">
          {#if bundle}
            <code class="font-mono">{bundle.version}</code>
            {#if bundle.builtAt}
              <span class="text-muma-spotify-text"> · {$t('settings.about.builtAt', { date: builtAtLabel(bundle.builtAt) })}</span>
            {/if}
          {:else}
            {$t('settings.about.unknown')}
          {/if}
        </dd>
      </dl>
    </section>

    {#if sourceUrl}
      <section class="bg-muma-spotify-panel rounded-lg p-6 shadow-lg border border-white/5" data-testid="about-source">
        <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.about.sourceCode')}</h2>
        <p class="text-muma-spotify-text text-sm mb-3">{$t('settings.about.sourceCodeBody')}</p>
        <a
          href={sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          class="text-brand text-sm font-bold break-all hover:underline"
          onclick={openSource}
        >{sourceUrl}</a>
      </section>
    {/if}

    <section class="bg-muma-spotify-panel rounded-lg p-6 shadow-lg border border-white/5">
      <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.about.howItWorksTitle')}</h2>

      <div>
        <h3 class="text-white font-bold mb-1">{$t('settings.about.howCarModeTitle')}</h3>
        <p class="text-muma-spotify-text text-sm">{$t('settings.about.howCarModeBody')}</p>
      </div>
    </section>

    <section class="bg-muma-spotify-panel rounded-lg p-6 shadow-lg border border-white/5">
      <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">
        {isNative ? $t('settings.about.releaseNotesApp') : $t('settings.about.whatsNew')}
      </h2>

      {#if isLoading}
        <p class="text-muma-spotify-text">{$t('common.loading')}</p>
      {:else if releaseNotes.length === 0}
        <p class="text-muma-spotify-text text-sm italic">{$t('settings.about.noReleaseNotes')}</p>
      {:else}
        <div class="flex flex-col gap-6">
          {#each releaseNotes as release (release.version)}
            <div class="border-l-2 border-brand pl-4">
              <div class="flex items-center gap-3 mb-2">
                <span class="text-white font-bold">{release.version}</span>
                <span class="text-xs text-muma-spotify-text">{release.date}</span>
              </div>
              <div class="text-sm space-y-3">
                {#each Object.entries(release.notes) as [category, items] (category)}
                  <div>
                    <span class="text-brand uppercase text-[10px] font-bold tracking-wider">{category}</span>
                    <ul class="list-disc list-inside mt-1 text-[#e5e5e5]">
                      {#each items as item, i (i)}
                        <li>{item}</li>
                      {/each}
                    </ul>
                  </div>
                {/each}
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </section>
  </div>
</div>

<style>
  .text-brand { color: #1ed760; }
  .border-brand { border-color: #1ed760; }
</style>
