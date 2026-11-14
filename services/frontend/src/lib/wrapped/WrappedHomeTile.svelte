<script>
  /**
   * The Wrapped banner on the web home screen, from 1 December to 31 January and only while the
   * "Show Wrapped on the home screen" setting is on. December offers the running year, January
   * the year that just ended. The phone home shows the same offer as a quick-access tile.
   */
  import { Gift } from '@lucide/svelte';
  import { t } from '../i18n/index.js';
  import { wrappedOnHomeEnabled } from '../store.js';
  import { homeTileYear, wrappedView } from './wrapped.js';

  const { onnavigate, now = new Date() } = $props();

  const year = $derived(homeTileYear(now));
  const running = $derived(year === now.getFullYear());
</script>

{#if $wrappedOnHomeEnabled && year}
  <button
    type="button"
    class="flex items-center gap-4 w-full rounded-lg p-5 border-none cursor-pointer text-left text-black hover:brightness-110 transition"
    style="background: linear-gradient(120deg, #1db954, #2d5afc);"
    data-testid="home-wrapped-tile"
    onclick={() => onnavigate(wrappedView(String(year), 'user'))}
  >
    <Gift size={40} />
    <span class="flex flex-col">
      <span class="text-2xl font-black">{$t('wrapped.home.title', { year })}</span>
      <span class="text-sm font-bold">{$t(running ? 'wrapped.home.textRunning' : 'wrapped.home.text')}</span>
    </span>
  </button>
{/if}
