<script>
  import { onMount } from 'svelte';
  import { fromStore } from 'svelte/store';
  import { t } from './i18n/index.js';
  import { platform as defaultPlatform } from './platform/index.js';
  import {
    viewMode,
    memoriesOnHomeEnabled,
    deduplicateEnabled,
    homeModeReleaseRadar,
    homeModeDailyMix,
    homeModeFavorites,
    homeModeRecentlyReleased,
    homeModeRecentlyAdded,
    trackListLines,
    showConfirmationDialog,
    setupStepsSeen,
  } from './store.js';
  import { markSeen } from './setup.js';
  import LanguageSetting from './settings/LanguageSetting.svelte';

  /**
   * The setup tour, one step per screen over the settings that decide how MuMa fits the
   * listener. Every control here is bound to the same store the settings pages write, so
   * a choice made in the tour is the choice the settings page shows afterwards and there
   * is no second copy of any setting to keep in step.
   *
   * `steps` is what to walk through -- the pending ones on a first run or after an update,
   * every step when started by hand from the manual -- and `update` says whether to badge
   * them as new. Finishing and skipping both record every step in `steps` as seen: a tour
   * that reopened until it was completed would be a nag, not a welcome.
   */
  const {
    steps = [],
    update = false,
    platform = defaultPlatform,
    onclose = () => {},
  } = $props();

  let index = $state(0);
  const step = $derived(steps[index]);
  const isLast = $derived(index >= steps.length - 1);

  // The same three-way choice GeneralSettings offers per Home section.
  const HOME_MODE_OPTIONS = [
    { value: 'OFF', labelKey: 'settings.general.home.modeOff' },
    { value: 'BUTTON', labelKey: 'settings.general.home.modeButton' },
    { value: 'OVERVIEW', labelKey: 'settings.general.home.modeOverview' },
  ];
  // `fromStore` rather than `$store`: the auto-subscription only works on a top-level
  // variable, and these are read inside an `{#each}`.
  const HOME_SECTIONS = [
    { store: homeModeReleaseRadar, labelKey: 'settings.general.home.releaseRadar' },
    { store: homeModeDailyMix, labelKey: 'settings.general.home.dailyMix' },
    { store: homeModeFavorites, labelKey: 'settings.general.home.favorites' },
    { store: homeModeRecentlyReleased, labelKey: 'settings.general.home.recentlyReleased' },
    { store: homeModeRecentlyAdded, labelKey: 'settings.general.home.recentlyAdded' },
  ].map((section) => ({ ...section, value: fromStore(section.store) }));

  // The phone's own wifi-only preference, read and written through the shell exactly as
  // GeneralSettings does; the step never renders outside `platform.storage.supported`.
  let wifiOnly = $state(false);
  onMount(async () => {
    if (!platform?.storage?.supported) return;
    try {
      const device = await platform.system.getSettings();
      wifiOnly = device?.wifiOnly === true;
    } catch (e) {
      console.error("Failed to load the device's wifi-only setting", e);
    }
  });
  async function toggleWifiOnly() {
    const next = !wifiOnly;
    wifiOnly = next;
    try {
      await platform.system.setSetting({ key: 'wifiOnly', value: next });
    } catch (e) {
      wifiOnly = !next;
      console.error("Failed to save the device's wifi-only setting", e);
    }
  }

  function finish(destination) {
    setupStepsSeen.update((seen) => markSeen(seen, steps));
    onclose(destination);
  }

  function next() {
    if (isLast) finish();
    else index += 1;
  }

  function back() {
    if (index > 0) index -= 1;
  }

  function handleKeydown(e) {
    if (e.key === 'Escape') finish();
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div
  class="fixed inset-0 z-50 bg-[#121212] text-white flex flex-col overflow-y-auto"
  role="dialog"
  aria-modal="true"
  aria-labelledby="setup-title"
  data-testid="setup-wizard"
>
  <div class="w-full max-w-2xl mx-auto flex flex-col flex-1 p-6 sm:p-10 gap-8">
    <header class="flex items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <img src="/images/logo.svg" alt="" class="w-10 h-10" onerror={(e) => (e.currentTarget.style.display = 'none')} />
        <span class="text-sm text-[#b3b3b3]">
          {update ? $t('setup.updateIntro') : $t('setup.welcome')}
        </span>
      </div>
      <button
        type="button"
        class="text-sm text-[#b3b3b3] hover:text-white bg-transparent border-none cursor-pointer"
        onclick={() => finish()}
      >
        {$t('setup.skip')}
      </button>
    </header>

    {#if step}
      <div class="flex items-center gap-2" aria-label={$t('setup.progress', { current: index + 1, total: steps.length })}>
        {#each steps as s, i (s.id)}
          <span class="h-1.5 flex-1 rounded-full {i <= index ? 'bg-brand' : 'bg-white/10'}"></span>
        {/each}
      </div>

      <section class="flex flex-col gap-4 flex-1" data-testid="setup-step-{step.id}">
        <div class="flex items-center gap-3">
          <p class="text-xs uppercase tracking-widest text-[#b3b3b3] m-0">
            {$t('setup.progress', { current: index + 1, total: steps.length })}
          </p>
          {#if update}
            <span class="text-[10px] font-black uppercase tracking-wider bg-brand text-black px-2 py-0.5 rounded-full">{$t('setup.new')}</span>
          {/if}
        </div>
        <h1 id="setup-title" class="text-3xl font-bold m-0">{$t(`setup.steps.${step.id}.title`)}</h1>
        <p class="text-[#b3b3b3] leading-relaxed m-0">{$t(`setup.steps.${step.id}.body`)}</p>

        <div class="mt-4 bg-[#181818] rounded-lg p-5 border border-white/5 flex flex-col gap-5">
          {#if step.id === 'language'}
            <LanguageSetting />
          {:else if step.id === 'mode'}
            <div class="flex gap-2" role="group" aria-label={$t('sidebar.toggleMode')}>
              <button
                type="button"
                class="flex-1 py-3 rounded-lg font-bold border-none cursor-pointer transition-colors {$viewMode === 'songs' ? 'bg-brand-green text-black' : 'bg-white/10 text-white'}"
                aria-pressed={$viewMode === 'songs'}
                onclick={() => viewMode.set('songs')}
              >{$t('nav.songs')}</button>
              <button
                type="button"
                class="flex-1 py-3 rounded-lg font-bold border-none cursor-pointer transition-colors {$viewMode === 'sets' ? 'bg-brand-blue text-black' : 'bg-white/10 text-white'}"
                aria-pressed={$viewMode === 'sets'}
                onclick={() => viewMode.set('sets')}
              >{$t('nav.sets')}</button>
            </div>
            <p class="text-xs text-[#b3b3b3] m-0">{$t('setup.steps.mode.hint')}</p>
          {:else if step.id === 'home'}
            {#each HOME_SECTIONS as section (section.labelKey)}
              <div class="flex items-center justify-between gap-4">
                <span class="font-bold">{$t(section.labelKey)}</span>
                <select
                  class="bg-[#282828] border border-white/10 rounded px-3 py-2 text-white focus:outline-none focus:border-brand"
                  aria-label={$t(section.labelKey)}
                  value={section.value.current}
                  onchange={(e) => section.store.set(e.currentTarget.value)}
                >
                  {#each HOME_MODE_OPTIONS as option (option.value)}
                    <option value={option.value}>{$t(option.labelKey)}</option>
                  {/each}
                </select>
              </div>
            {/each}
            <label class="flex items-center justify-between gap-4 cursor-pointer">
              <span class="font-bold">{$t('settings.general.memoriesOnHome')}</span>
              <input
                type="checkbox"
                class="w-5 h-5 accent-[#1db954]"
                checked={$memoriesOnHomeEnabled}
                onchange={() => memoriesOnHomeEnabled.update((v) => !v)}
              />
            </label>
          {:else if step.id === 'display'}
            <label class="flex items-center justify-between gap-4 cursor-pointer">
              <span class="flex flex-col gap-0.5">
                <span class="font-bold">{$t('settings.general.dedupe')}</span>
                <span class="text-xs text-[#b3b3b3]">{$t('settings.general.dedupeHelp')}</span>
              </span>
              <input
                type="checkbox"
                class="w-5 h-5 accent-[#1db954]"
                checked={$deduplicateEnabled}
                onchange={() => deduplicateEnabled.update((v) => !v)}
              />
            </label>
            <div class="flex items-center justify-between gap-4">
              <span class="font-bold">{$t('settings.general.display.trackListLines')}</span>
              <select
                class="bg-[#282828] border border-white/10 rounded px-3 py-2 text-white focus:outline-none focus:border-brand"
                aria-label={$t('settings.general.display.trackListLines')}
                value={$trackListLines}
                onchange={(e) => trackListLines.set(Number(e.currentTarget.value))}
              >
                <option value={2}>{$t('settings.general.display.trackListLinesCompact')}</option>
                <option value={3}>{$t('settings.general.display.trackListLinesDetailed')}</option>
              </select>
            </div>
            <label class="flex items-center justify-between gap-4 cursor-pointer">
              <span class="font-bold">{$t('settings.general.display.showConfirmationDialog')}</span>
              <input
                type="checkbox"
                class="w-5 h-5 accent-[#1db954]"
                checked={$showConfirmationDialog}
                onchange={() => showConfirmationDialog.update((v) => !v)}
              />
            </label>
          {:else if step.id === 'downloads'}
            <label class="flex items-center justify-between gap-4 cursor-pointer">
              <span class="flex flex-col gap-0.5">
                <span class="font-bold">{$t('settings.general.wifiOnly')}</span>
                <span class="text-xs text-[#b3b3b3]">{$t('settings.general.wifiOnlyHelp')}</span>
              </span>
              <input type="checkbox" class="w-5 h-5 accent-[#1db954]" checked={wifiOnly} onchange={toggleWifiOnly} />
            </label>
          {:else if step.id === 'guide'}
            <button
              type="button"
              class="self-start bg-white/10 hover:bg-white/20 text-white font-bold text-sm px-4 py-2 rounded-full border-none cursor-pointer transition-colors"
              onclick={() => finish('help')}
            >
              {$t('setup.steps.guide.open')}
            </button>
          {/if}
        </div>
      </section>

      <footer class="flex items-center justify-between gap-4 pt-4 border-t border-white/10">
        <button
          type="button"
          class="text-sm font-bold text-[#b3b3b3] hover:text-white bg-transparent border-none cursor-pointer disabled:opacity-30 disabled:cursor-default"
          disabled={index === 0}
          onclick={back}
        >
          {$t('setup.back')}
        </button>
        <button
          type="button"
          class="bg-brand text-black font-bold py-3 px-8 rounded-full border-none cursor-pointer hover:scale-105 transition-transform"
          onclick={next}
        >
          {isLast ? $t('setup.done') : $t('setup.next')}
        </button>
      </footer>
    {:else}
      <!-- Nothing to walk through (every step already seen, opened at a stale URL): say so
           and offer the way out rather than a blank screen. -->
      <section class="flex flex-col gap-4 flex-1">
        <h1 id="setup-title" class="text-3xl font-bold m-0">{$t('setup.nothingTitle')}</h1>
        <p class="text-[#b3b3b3] m-0">{$t('setup.nothingBody')}</p>
      </section>
      <footer class="flex justify-end pt-4 border-t border-white/10">
        <button
          type="button"
          class="bg-brand text-black font-bold py-3 px-8 rounded-full border-none cursor-pointer"
          onclick={() => finish()}
        >{$t('setup.done')}</button>
      </footer>
    {/if}
  </div>
</div>
