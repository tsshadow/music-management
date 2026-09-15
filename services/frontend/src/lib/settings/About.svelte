<script>
  import "./density.css";
  import { t } from '../i18n/index.js';
  import { onMount } from 'svelte';
  import { authParams, restUrl } from '../store.js';

  let version = $state('');
  let isLoading = $state(true);
  let releaseNotes = $state([]);

  /**
   * Fetches the running server version and the release notes shown to users.
   */
  async function loadInfo() {
    try {
      const response = await fetch(restUrl(`/rest/ping?${$authParams}`));
      const data = await response.json();
      const res = data['subsonic-response'];
      if (res) {
        version = res.serverVersion || res.version || '';
      }
    } catch (e) {
      console.error(e);
    }

    try {
      const rnResponse = await fetch('/release-notes.json');
      if (rnResponse.ok) {
        releaseNotes = await rnResponse.json();
      }
    } catch (e) {
      console.error(e);
    } finally {
      isLoading = false;
    }
  }

  onMount(loadInfo);
</script>

<div class="settings-density max-w-4xl pb-24">
  <header class="mb-8">
    <h1 class="text-3xl font-bold mb-2">{$t('settings.about.title')}</h1>
    <p class="text-[#b3b3b3]">{$t('settings.about.subtitle')}</p>
  </header>

  <div class="flex flex-col gap-8">
    <section class="bg-[#181818] rounded-lg p-6 shadow-lg border border-white/5">
      <div class="flex items-center gap-6">
        <img
          src="/images/logo.svg"
          alt=""
          class="w-20 h-20"
          onerror={(e) => (e.currentTarget.src = '/images/spotify-fallback.svg')}
        />
        <div>
          <h2 class="text-white text-2xl font-bold">MuMa</h2>
          <p class="text-[#b3b3b3]">
            {#if isLoading}
              Versie laden...
            {:else if version}
              Versie {version}
            {:else}
              Versie onbekend
            {/if}
          </p>
        </div>
      </div>
      <p class="text-[#b3b3b3] text-sm mt-6">
        {$t('settings.about.blurb')}
      </p>
    </section>

    <section class="bg-[#181818] rounded-lg p-6 shadow-lg border border-white/5">
      <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.about.howItWorksTitle')}</h2>

      <div>
        <h3 class="text-white font-bold mb-1">{$t('settings.about.howCarModeTitle')}</h3>
        <p class="text-[#b3b3b3] text-sm">{$t('settings.about.howCarModeBody')}</p>
      </div>
    </section>

    <section class="bg-[#181818] rounded-lg p-6 shadow-lg border border-white/5">
      <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.about.whatsNew')}</h2>

      {#if isLoading}
        <p class="text-[#b3b3b3]">{$t('common.loading')}</p>
      {:else if releaseNotes.length === 0}
        <p class="text-[#b3b3b3] text-sm italic">{$t('settings.about.noReleaseNotes')}</p>
      {:else}
        <div class="flex flex-col gap-6">
          {#each releaseNotes as release (release.version)}
            <div class="border-l-2 border-brand pl-4">
              <div class="flex items-center gap-3 mb-2">
                <span class="text-white font-bold">{release.version}</span>
                <span class="text-xs text-[#b3b3b3]">{release.date}</span>
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
