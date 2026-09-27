<script>
  import { queueContinuation } from './store.js';
  import { extendQueue } from './listContinuation.js';
  import ListEnd from './ListEnd.svelte';

  /**
   * The end of the queue, for a queue that came from a paged list (docs/designs/list-continuation/).
   *
   * The player tops such a queue up on its own once the current track is near the end
   * (`listContinuation.js`), which is right for listening and invisible for looking
   * (docs/bug-reports/122-feed-load-more-not-visible.md). So the queue ends like the list it came
   * from: the load-more pill while the list has a next page -- a tap fetches it now -- and "Einde
   * van de lijst" once it ran out. A failed request keeps the pill, so a second tap tries again. A
   * queue that never continued (an album, a playlist) ends in neither.
   *
   * Started as the feed-only `QueueFeedLoadMore` (bug report 122); every paged list uses it since
   * issue #100.
   *
   * @param {{loadMore?: (options: {force: boolean}) => Promise<boolean>}} props - `loadMore` is
   *   injected by the tests.
   */
  const { loadMore = extendQueue } = $props();

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

<ListEnd
  hasMore={$queueContinuation != null && !$queueContinuation.exhausted && $queueContinuation.cursor != null}
  ended={$queueContinuation?.exhausted === true}
  {loading}
  onmore={more}
  testid="queue-load-more"
/>
