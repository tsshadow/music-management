<script>
  import { t } from './i18n/index.js';
  import { authParams, playlist, currentTrack, playerState, viewMode, mumaUser } from './store.js';
  import { listOf, subsonicJson } from './subsonic.js';
  import { presetQuery, presetSummary, deletePreset, refreshPresets } from './presets.js';
  import { notify } from './notifications.js';
  import TrackList from './TrackList.svelte';

  /**
   * One preset, whole: the tracks its saved query answers with, a play button, and the way to
   * throw the preset away. Opened from a home tile, or from the phone's back stack after one.
   *
   * The list is fetched in pages of `PAGE` until the preset's own size is reached or LMS runs
   * out. A random preset carries one seed for the whole visit, so page two is the rest of the
   * same shuffle and not a fresh one that repeats page one.
   */
  const { preset, onnavigate } = $props();

  const PAGE = 100;

  let tracks = $state([]);
  let isLoading = $state(true);
  let isDeleting = $state(false);
  let menuOpen = $state(false);

  const subtitle = $derived(presetSummary(preset, $t));

  $effect(() => {
    const auth = $authParams;
    const which = preset?.id;
    const mode = $viewMode;
    if (!auth || !preset) return;

    isLoading = true;
    tracks = [];
    // Pages land as they arrive rather than all at once: a rating floor makes LMS slow, and the
    // play button is usable after the first hundred instead of after the fifth.
    load(preset, mode, (page) => {
      if (which === preset?.id) tracks = [...tracks, ...page];
    }).finally(() => {
      if (which === preset?.id) isLoading = false;
    });
  });

  async function load(target, mode, onPage) {
    const seed = Math.floor(Math.random() * 1_000_000);
    for (let offset = 0; offset < target.size; offset += PAGE) {
      const count = Math.min(PAGE, target.size - offset);
      const { method, params } = presetQuery(target, { viewMode: mode, count, offset, seed });
      let page;
      try {
        page = listOf(await subsonicJson(method, params), 'songs.song');
      } catch (error) {
        console.error('Could not load the preset', error);
        return;
      }
      onPage(page);
      if (page.length < count) return;
    }
  }

  /** Queues the whole list in its order and starts it. */
  function playAll() {
    if (tracks.length === 0) return;
    playlist.set(tracks);
    currentTrack.set(tracks[0]);
    playerState.update((s) => ({ ...s, playing: true }));
  }

  async function remove() {
    menuOpen = false;
    if (!confirm($t('presets.deleteConfirm', { name: preset.name }))) return;
    isDeleting = true;
    try {
      await deletePreset($mumaUser?.id, preset.id);
      await refreshPresets($mumaUser?.id);
      notify.success($t('presets.deleted'));
      onnavigate?.('home');
    } catch (error) {
      console.error(error);
      notify.error($t('presets.deleteFailed'));
    } finally {
      isDeleting = false;
    }
  }
</script>

<div class="flex flex-col gap-8 pb-12">
  <header class="flex items-start justify-between gap-4">
    <div class="min-w-0">
      <div class="text-xs font-bold uppercase tracking-wider mb-2 text-[#b3b3b3]">{$t('presets.one')}</div>
      <h1 class="text-3xl md:text-5xl font-black mb-3 break-words">{preset.name}</h1>
      <div class="flex items-center gap-2 text-sm font-medium flex-wrap">
        <span class="text-white">{subtitle}</span>
        {#if tracks.length > 0}
          <span class="text-[#b3b3b3]">• {$t('common.trackCount', { count: tracks.length })}</span>
        {/if}
      </div>
    </div>
    {#if $mumaUser}
      <div class="relative shrink-0">
        <button
          class="bg-transparent border-none text-[#b3b3b3] hover:text-white cursor-pointer p-2"
          aria-label={$t('common.more')}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          onclick={() => (menuOpen = !menuOpen)}
        >
          <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor" aria-hidden="true">
            <path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"></path>
          </svg>
        </button>
        {#if menuOpen}
          <div class="absolute right-0 top-full mt-1 w-48 bg-[#282828] rounded-md shadow-xl border border-white/5 py-1 z-30" role="menu">
            <button
              class="w-full text-left px-4 py-2 text-sm text-white hover:bg-white/10 bg-transparent border-none cursor-pointer"
              role="menuitem"
              onclick={() => { menuOpen = false; onnavigate?.(`preset-edit:${preset.id}`); }}
            >{$t('presetBuilder.edit')}</button>
            <button
              class="w-full text-left px-4 py-2 text-sm text-white hover:bg-white/10 bg-transparent border-none cursor-pointer disabled:opacity-50"
              role="menuitem"
              disabled={isDeleting}
              onclick={remove}
            >{$t('presets.delete')}</button>
          </div>
        {/if}
      </div>
    {/if}
  </header>

  <div>
    <div class="flex items-center gap-8 mb-8">
      {#if tracks.length > 0}
        <button
          class="bg-brand text-black w-14 h-14 rounded-full flex items-center justify-center shadow-xl hover:scale-105 active:scale-95 transition cursor-pointer border-none"
          onclick={playAll}
          title={$t('common.playAll')}
          aria-label={$t('common.playAll')}
        >
          <svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor">
            <path d="M7 6v12l10-6z"></path>
          </svg>
        </button>
      {/if}
    </div>

    {#if isLoading && tracks.length === 0}
      <div class="text-[#b3b3b3] p-12 text-center">{$t('common.loading')}</div>
    {:else if tracks.length === 0}
      <div class="text-[#b3b3b3] p-12 text-center">{$t('presets.empty')}</div>
    {:else}
      <TrackList {tracks} onnavigate={onnavigate} />
    {/if}
  </div>
</div>
