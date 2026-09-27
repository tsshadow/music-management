<script>
  import { t } from './i18n/index.js';
  import { feedContinuation } from './store.js';
  import { extendFeedQueue } from './feedQueue.js';

  /**
   * "Meer laden" under the queue, for a queue that came from a feed.
   *
   * The player tops a feed queue up on its own once the current track is near the end
   * (`feedQueue.js`), which is right for listening and invisible for looking: the queue showed the
   * first page and nothing said there was more (docs/bug-reports/122-feed-load-more-not-visible.md).
   * This is the same outlined pill the feed page and the song lists end in (docs/styleguide.md,
   * "Load more"), rendered only while the queue's feed has a next page. A failed request keeps
   * it, so a second tap tries again; a page that says there is no more removes it.
   *
   * @param {{loadMore?: (options: {force: boolean}) => Promise<boolean>}} props - `loadMore` is
   *   injected by the tests.
   */
  const { loadMore = extendFeedQueue } = $props();

  let loading = $state(false);

  async function more() {
    if (loading) return;
    loading = true;
    try {
      await loadMore({ force: true });
    } finally {
      loading = false;
    }
  }
</script>

{#if $feedContinuation?.nextOffset}
  <div class="flex justify-center py-6">
    <button
      class="bg-transparent border border-muma-spotify-muted text-white px-8 py-2 rounded-[24px] font-bold cursor-pointer transition-all hover:border-white hover:scale-[1.04] disabled:cursor-default"
      onclick={more}
      disabled={loading}
      data-testid="queue-load-more"
    >
      {loading ? $t('common.loading') : $t('common.loadMore')}
    </button>
  </div>
{/if}
