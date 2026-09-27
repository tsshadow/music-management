<script>
  import { t } from './i18n/index.js';
  import { untrack } from 'svelte';
  import { authParams, trackPageSize } from './store.js';
  import TrackList from './TrackList.svelte';
  import ListEnd from './ListEnd.svelte';
  import SectionState from './loading/SectionState.svelte';
  import SkeletonRows from './loading/SkeletonRows.svelte';
  import Throbber from './loading/Throbber.svelte';
  import { fetchHistoryPage, historyContinuation } from './trackPages.js';

  const { onnavigate } = $props();

  let history = $state([]);
  // Starts true: the first frame is the skeleton, never the "no history" line.
  let isLoading = $state(true);
  // The first page failed: the list offers a retry instead of claiming the history is empty.
  let failed = $state(false);
  // A reload of the first page while rows are on screen (the Refresh button).
  let refreshing = $state(false);
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
    if (!append) {
        failed = false;
        refreshing = history.length > 0;
    }
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
        // A failed refresh keeps the rows on screen; only a first load with nothing to show
        // turns into the error line.
        if (!append && history.length === 0) failed = true;
        hasMore = false;
    } finally {
        isLoading = false;
        refreshing = false;
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
        class="bg-muma-spotify-light text-white px-4 py-2 rounded-full font-bold hover:scale-105 transition-transform flex items-center gap-2"
        onclick={() => loadHistory(false)}
    >
        <!-- A refresh keeps the list on screen (styleguide, Loading States: Refresh); the
             throbber says a newer one is on its way. -->
        {#if refreshing}<Throbber size={14} />{/if}
        {$t('common.refresh')}
    </button>
  </div>

  {#if history.length > 0}
    <TrackList tracks={history} showDate={true} {continuation} onnavigate={onnavigate} />
    <ListEnd {hasMore} ended={pagedMore} loading={isLoading} onmore={() => loadHistory(true)} testid="history-load-more" />
  {:else if isLoading || failed}
    <SectionState status={failed ? 'error' : 'loading'} onretry={() => loadHistory(false)}>
      {#snippet skeleton()}
        <SkeletonRows count={10} />
      {/snippet}
    </SectionState>
  {:else}
    <div class="text-center py-20">
      <p class="text-muma-spotify-text text-lg">{$t('history.empty')}</p>
    </div>
  {/if}
</div>
