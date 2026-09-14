<script>
  /**
   * What is on this device.
   *
   * Absent in a browser: the drawer and the tab strip only list it when
   * `platform.storage.supported`, and landing on `/downloads` anyway says so
   * rather than showing an empty list somebody would read as "my downloads are
   * gone" (acceptance criterion 13).
   *
   * The list is `platform.storage.list()` grouped by `downloads.js`; the states
   * are kept live by the `progress` event, which is also the only thing that
   * can change the total, so it re-reads `size()` on a state change rather than
   * polling. Removing is a long press, as the functional design asks -- with a
   * visible button beside it, because a long press is not reachable with a
   * keyboard and this screen is the same code on a desktop.
   */
  import { onMount } from 'svelte';
  import { t, locale } from './i18n/index.js';
  import { platform as defaultPlatform } from './platform/index.js';
  import { formatBytes, groupDownloads, groupProgress, groupState } from './downloads.js';
  import { logAction } from './diagnosticsLog.js';
  import { currentTrack, playerState, playlist } from './store.js';
  import { notify } from './notifications.js';

  const { platform = defaultPlatform, onnavigate = null } = $props();

  /** How long a press has to last to count as "remove this", in milliseconds. */
  const LONG_PRESS_MS = 600;

  const supported = $derived(platform?.storage?.supported === true);

  let items = $state([]);
  let totalBytes = $state(0);
  let isLoading = $state(true);
  let pendingRemoval = $state(null);
  let pressTimer = null;

  const groups = $derived(groupDownloads(items));
  const estimated = $derived(groups.some((group) => group.estimated));

  /** Re-reads the whole list and the total. Cheap enough: it is one bridge hop each. */
  async function refresh() {
    if (!supported) {
      isLoading = false;
      return;
    }
    try {
      const [list, bytes] = await Promise.all([platform.storage.list(), platform.storage.size()]);
      items = list;
      totalBytes = bytes;
    } catch (error) {
      console.error('Could not read what is downloaded', error);
    } finally {
      isLoading = false;
    }
  }

  onMount(() => {
    refresh();
    if (!supported) return;
    // A state change is also the only thing that can move the total, so the
    // same event drives both and nothing polls.
    return platform.storage.onProgress((event) => {
      items = items.map((item) =>
        String(item.id) === String(event.id)
          ? { ...item, state: event.state, progress: event.progress }
          : item
      );
      if (event.state === 'done' || event.state === 'failed') refresh();
    });
  });

  /**
   * Plays a group from its first item, which is what tapping a row means
   * everywhere else in the app.
   *
   * @param {{items: Array<object>}} group
   */
  function playGroup(group) {
    if (!group.items.length) return;
    playlist.set(group.items);
    currentTrack.set(group.items[0]);
    playerState.update((state) => ({ ...state, playing: true }));
  }

  /**
   * @param {{items: Array<{id: string}>, title: string}} group
   */
  async function remove(group) {
    pendingRemoval = null;
    logAction('download.cancel', { group: group.key, tracks: group.items.length });
    try {
      await platform.storage.remove(group.items.map((item) => item.id));
      notify.success($t('downloads.removed', { title: group.title }));
      await refresh();
    } catch (error) {
      console.error('Could not remove a download', error);
      notify.error($t('downloads.removeFailed'), { detail: error.message });
    }
  }

  /** @param {{key: string}} group */
  function startPress(group) {
    clearTimeout(pressTimer);
    pressTimer = setTimeout(() => (pendingRemoval = group.key), LONG_PRESS_MS);
  }

  function endPress() {
    clearTimeout(pressTimer);
  }

  /**
   * @param {{items: Array<{id: string}>}} group
   * @returns {number} 0..100.
   */
  function progressOf(group) {
    return Math.round(groupProgress(group));
  }
</script>

<div class="flex flex-col gap-6" data-testid="downloads-view">
  <header class="flex flex-wrap justify-between items-end gap-2">
    <div>
      <h1 class="text-3xl font-bold m-0">{$t('nav.downloads')}</h1>
      {#if supported}
        <p class="text-[#b3b3b3] text-sm mt-1" data-testid="downloads-total">
          {$t('downloads.total', {
            size: formatBytes(totalBytes, $locale),
            count: items.length
          })}
        </p>
      {/if}
    </div>
  </header>

  {#if !supported}
    <div class="text-[#b3b3b3] p-12 text-center border border-white/5 rounded-xl bg-white/5">
      <p class="text-xl font-bold mb-2 text-white">{$t('downloads.browserTitle')}</p>
      <p class="text-sm opacity-60">{$t('downloads.browserHelp')}</p>
    </div>
  {:else if isLoading}
    <p class="text-[#b3b3b3] animate-pulse">{$t('common.loading')}</p>
  {:else if groups.length === 0}
    <div class="text-[#b3b3b3] p-12 text-center border border-white/5 rounded-xl bg-white/5">
      <p class="text-xl font-bold mb-2 text-white">{$t('downloads.emptyTitle')}</p>
      <p class="text-sm opacity-60">{$t('downloads.emptyHelp')}</p>
      {#if onnavigate}
        <button
          class="mt-4 bg-transparent border border-[#727272] text-white px-6 py-2 rounded-[24px] font-bold cursor-pointer transition-all hover:border-white hover:scale-[1.04]"
          onclick={() => onnavigate('songs')}
        >{$t('downloads.discover')}</button>
      {/if}
    </div>
  {:else}
    {#if estimated}
      <p class="text-[11px] text-[#b3b3b3] opacity-70">{$t('downloads.estimatedNote')}</p>
    {/if}
    <ul class="list-none p-0 m-0 flex flex-col gap-1">
      {#each groups as group (group.key)}
        {@const state = groupState(group)}
        <li class="rounded" data-testid="download-group">
          <div
            role="button"
            tabindex="0"
            class="w-full flex items-center gap-3 px-3 py-3 rounded hover:bg-white/10 cursor-pointer select-none text-left"
            onclick={() => playGroup(group)}
            onkeydown={(e) => e.key === 'Enter' && playGroup(group)}
            onpointerdown={() => startPress(group)}
            onpointerup={endPress}
            onpointerleave={endPress}
          >
            <span
              class="w-8 h-8 flex-shrink-0 flex items-center justify-center rounded-full {state === 'failed' ? 'text-red-400' : state === 'done' ? 'text-brand' : 'text-[#b3b3b3]'}"
              aria-label={$t(`downloads.state.${state}`)}
              title={$t(`downloads.state.${state}`)}
            >
              {#if state === 'done'}
                <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm-1 14.4L6.6 12 8 10.6l3 3 5-5L17.4 10 11 16.4z"></path></svg>
              {:else if state === 'failed'}
                <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"></path></svg>
              {:else if state === 'running'}
                <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" class="animate-pulse"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"></path></svg>
              {:else}
                <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M11 7h2v6h-2zM12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 18a8 8 0 1 1 0-16 8 8 0 0 1 0 16z"></path></svg>
              {/if}
            </span>

            <div class="flex flex-col min-w-0 flex-1">
              <span class="text-white text-sm md:text-base font-medium truncate">
                {group.title}
                {#if group.isSet}
                  <span class="ml-2 text-[10px] uppercase tracking-wider text-brand align-middle">{$t('nav.sets')}</span>
                {/if}
              </span>
              <span class="text-xs text-[#b3b3b3] truncate">
                {group.subtitle}
                {#if group.subtitle}<span aria-hidden="true"> · </span>{/if}
                {$t('common.trackCount', { count: group.items.length })}
                <span aria-hidden="true"> · </span>{formatBytes(group.bytes, $locale)}
              </span>
              {#if state === 'running' || state === 'queued'}
                <span class="mt-1 block h-1 w-full bg-white/10 rounded-full overflow-hidden">
                  <span class="block h-full bg-brand" style="width: {progressOf(group)}%"></span>
                </span>
              {/if}
            </div>

            {#if state === 'failed'}
              <button
                class="bg-transparent border border-[#727272] text-white text-xs px-3 py-1 rounded-full cursor-pointer hover:border-white"
                onclick={(e) => { e.stopPropagation(); logAction('download.start', { group: group.key, tracks: group.items.length }); platform.storage.download(group.items.map((item) => item.id), { pin: true }); }}
              >{$t('downloads.retry')}</button>
            {/if}

            <button
              aria-label={$t('downloads.remove')}
              title={$t('downloads.remove')}
              class="bg-transparent border-none text-[#b3b3b3] cursor-pointer p-2 rounded hover:bg-[#333] hover:text-white"
              onclick={(e) => { e.stopPropagation(); pendingRemoval = group.key; }}
            >
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M6 19c0 1.1.9 2 2 2h8a2 2 0 0 0 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"></path></svg>
            </button>
          </div>

          {#if pendingRemoval === group.key}
            <div class="flex items-center justify-between gap-3 px-3 py-2 bg-[#282828] rounded-b text-sm" data-testid="remove-confirm">
              <span>{$t('downloads.removeConfirm', { title: group.title, size: formatBytes(group.bytes, $locale) })}</span>
              <span class="flex gap-2 flex-shrink-0">
                <button
                  class="bg-transparent border border-[#727272] text-white px-4 py-1 rounded-full cursor-pointer hover:border-white"
                  onclick={() => (pendingRemoval = null)}
                >{$t('common.cancel')}</button>
                <button
                  class="bg-brand text-black font-bold px-4 py-1 rounded-full cursor-pointer"
                  onclick={() => remove(group)}
                >{$t('downloads.remove')}</button>
              </span>
            </div>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</div>
