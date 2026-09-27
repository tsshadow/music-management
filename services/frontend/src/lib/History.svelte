<script>
  import { t } from './i18n/index.js';
  import { untrack } from 'svelte';
  import { authParams, trackPageSize } from './store.js';
  import TrackList from './TrackList.svelte';
  import ListEnd from './ListEnd.svelte';
  import { fetchHistoryPage, historyContinuation } from './trackPages.js';

  const { onnavigate } = $props();

  let history = $state([]);
  let isLoading = $state(false);
  let offset = $state(0);
  const pageSize = $derived($trackPageSize);
  let hasMore = $state(true);

  // Whether "Meer laden" appended anything, so a history that ran out says "Einde van de lijst".
  let pagedMore = $state(false);

  /**
   * Where the history continues, for a queue started by tapping one of its rows
   * (docs/designs/list-continuation/). A song heard twice is queued once.
   */
  const continuation = $derived(
    hasMore && history.length > 0 ? historyContinuation(offset, { pageSize }) : null
  );

  /**
   * Loads the listen history from the backend.
   *
   * @param {boolean} [append=false] - Whether to append results to the existing list.
   */
  async function loadHistory(append = false) {
    if (!$authParams) return;
    if (!append) {
        offset = 0;
        hasMore = true;
        pagedMore = false;
    }
    if (!hasMore) return;

    isLoading = true;
    try {
        const page = await fetchHistoryPage(offset, pageSize, $authParams);
        if (append) {
            history = [...history, ...page.entries];
            pagedMore = true;
        } else {
            history = page.entries;
        }
        hasMore = page.hasMore;
        offset += page.entries.length;
    } catch (e) {
        console.error("Failed to load history:", e);
    } finally {
        isLoading = false;
    }
  }

  $effect(() => {
    if ($authParams) {
        untrack(() => loadHistory());
    }
  });
</script>

<div class="p-8">
  <div class="flex items-center justify-between mb-8">
    <div>
      <h2 class="text-3xl font-bold mb-2">{$t('history.title')}</h2>
      <p class="text-muma-spotify-text">{$t('history.subtitle')}</p>
    </div>
    <button 
        class="bg-muma-spotify-light text-white px-4 py-2 rounded-full font-bold hover:scale-105 transition-transform"
        onclick={() => loadHistory(false)}
    >
        {$t('common.refresh')}
    </button>
  </div>

  {#if history.length > 0}
    <TrackList tracks={history} showDate={true} {continuation} onnavigate={onnavigate} />
    <ListEnd {hasMore} ended={pagedMore} loading={isLoading} onmore={() => loadHistory(true)} testid="history-load-more" />
  {:else if isLoading}
    <div class="flex justify-center py-20">
      <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-brand"></div>
    </div>
  {:else}
    <div class="text-center py-20">
      <p class="text-muma-spotify-text text-lg">{$t('history.empty')}</p>
    </div>
  {/if}
</div>
