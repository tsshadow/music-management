<script>
  /**
   * Placeholder cards on the entity pages' card grid (three columns on the phone, auto-filled
   * 180px columns from `md`): a square cover, or a round portrait with `round`, and a title line.
   */
  import { t } from '../i18n/index.js';
  import Skeleton from './Skeleton.svelte';

  const { count = 6, round = false } = $props();
</script>

<div
  class="grid grid-cols-3 gap-3 md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] md:gap-6"
  role="status"
  aria-label={$t('common.loading')}
  data-testid="skeleton-tiles"
>
  {#each Array.from({ length: count }, (_, i) => i) as i (i)}
    <div class="bg-muma-spotify-panel p-2 md:p-4 rounded-lg">
      <Skeleton class="w-full aspect-square mb-2 md:mb-4 {round ? 'rounded-full' : ''}" />
      <Skeleton class="h-3.5 w-3/4 mb-2" />
      <Skeleton class="h-3 w-1/2" />
    </div>
  {/each}
</div>
