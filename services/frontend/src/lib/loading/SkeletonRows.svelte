<script>
  /**
   * Placeholder rows in TrackList's geometry (`h-14 md:h-16`, a 48px cover, a title line and an
   * artist line), shown where a track list is on its way. Announced once as "loading".
   */
  import { t } from '../i18n/index.js';
  import Skeleton from './Skeleton.svelte';

  const { count = 8 } = $props();

  // Varying widths read as text; identical bars read as a table of nothing.
  const TITLE_WIDTHS = ['w-2/5', 'w-1/2', 'w-1/3', 'w-3/5', 'w-2/5', 'w-1/2'];
  const ARTIST_WIDTHS = ['w-1/4', 'w-1/5', 'w-1/3', 'w-1/4', 'w-1/6', 'w-1/5'];
</script>

<div role="status" aria-label={$t('common.loading')} data-testid="skeleton-rows">
  {#each Array.from({ length: count }, (_, i) => i) as i (i)}
    <div class="flex items-center gap-3 h-14 md:h-16 px-4">
      <Skeleton class="w-12 h-12 shrink-0" />
      <div class="flex flex-col gap-2 flex-1 min-w-0">
        <Skeleton class="h-3.5 {TITLE_WIDTHS[i % TITLE_WIDTHS.length]}" />
        <Skeleton class="h-3 {ARTIST_WIDTHS[i % ARTIST_WIDTHS.length]}" />
      </div>
    </div>
  {/each}
</div>
