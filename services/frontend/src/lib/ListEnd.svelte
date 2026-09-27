<script>
  import { t } from './i18n/index.js';

  /**
   * The end of a list that continues: the "Meer laden" pill while there is more, the muted
   * "Einde van de lijst" line once a list that did continue has run out, nothing for a list that
   * never had more (docs/styleguide.md, "Load more"; docs/designs/list-continuation/).
   *
   * One component for the pages and the queue, so the two cannot drift apart. Presentational
   * only: the caller owns the paging and says which of the three states applies.
   *
   * @param {{
   *   hasMore?: boolean,
   *   ended?: boolean,
   *   loading?: boolean,
   *   onmore?: () => void,
   *   testid?: string
   * }} props - `ended` is only read when `hasMore` is false; `testid` names the pill for tests,
   *   and the end line gets the same id with `-end` appended.
   */
  const { hasMore = false, ended = false, loading = false, onmore, testid = 'list-load-more' } = $props();
</script>

{#if hasMore}
  <div class="flex justify-center py-6">
    <button
      class="bg-transparent border border-muma-spotify-muted text-white px-8 py-2 rounded-[24px] font-bold cursor-pointer transition-all hover:border-white hover:scale-[1.04] disabled:cursor-default"
      onclick={() => onmore?.()}
      disabled={loading}
      data-testid={testid}
    >
      {loading ? $t('common.loading') : $t('common.loadMore')}
    </button>
  </div>
{:else if ended}
  <p class="text-center text-muma-spotify-text text-sm py-6 m-0" data-testid={`${testid}-end`}>
    {$t('common.endOfList')}
  </p>
{/if}
