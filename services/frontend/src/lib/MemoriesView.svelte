<script>
  import { t } from './i18n/index.js';
  import { onMount } from 'svelte';
  import { authParams, restUrl } from './store.js';
  import MemoryYearCard from './MemoryYearCard.svelte';
  import Skeleton from './loading/Skeleton.svelte';
  import { memoriesUrl, parseMemoryGroups, playMemoryYear, yearTiles } from './memories.js';

  const { onnavigate } = $props();

  let groups = $state([]);
  let isLoading = $state(true);

  const tiles = $derived(yearTiles(groups));

  /**
   * Loads today's memories.
   *
   * The browser's own local date is sent along so that the groups match the device's today rather
   * than the server's, which matters as soon as the two are in different time zones. Only a handful
   * of songs per year is asked for: the server ranks a year before truncating it and reports the
   * year's real size, so a tile can name its best three and count the whole year off a short page.
   */
  async function loadMemories() {
    if (!$authParams) return;
    isLoading = true;
    try {
      const response = await fetch(restUrl(memoriesUrl($authParams)));
      if (response.ok) {
        const data = await response.json();
        groups = parseMemoryGroups(data);
      }
    } catch (e) {
      // An older or non-LMS server simply has no memories; that is not an error worth showing.
      console.error('Failed to load memories:', e);
      groups = [];
    } finally {
      isLoading = false;
    }
  }

  onMount(loadMemories);

  /** Plays one year, in the order the server sent it. See `playMemoryYear` for the fetch/fallback rule. */
  function playYear(year) {
    return playMemoryYear(year, groups, $authParams);
  }

  /** Opens one year's own page. */
  function openYear(year) {
    onnavigate(`memories:${year}`);
  }
</script>

<div class="flex flex-col gap-8 pb-12">
  <header class="mb-2">
    <h1 class="text-4xl md:text-6xl font-black mb-2">{$t('memories.title')}</h1>
    <p class="text-muma-spotify-text">{$t('memories.subtitle')}</p>
  </header>

  {#if isLoading}
    <!-- Year tiles in the real grid's geometry: a square cover and the line under it
         (issue #112, styleguide Loading States). -->
    <div class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4 md:gap-6" role="status" aria-label={$t('common.loading')} data-testid="skeleton-tiles">
      {#each [0, 1, 2, 3] as i (i)}
        <div class="flex flex-col bg-muma-spotify-panel rounded-lg overflow-hidden">
          <Skeleton class="w-full aspect-square rounded-none" />
          <div class="p-4 flex flex-col gap-2">
            <Skeleton class="h-3.5 w-3/4" />
            <Skeleton class="h-3 w-1/2" />
          </div>
        </div>
      {/each}
    </div>
  {:else if tiles.length === 0}
    <div class="flex flex-col gap-2">
      <p class="text-white font-bold">{$t('memories.empty')}</p>
      <p class="text-muma-spotify-text">{$t('memories.emptyHelp')}</p>
    </div>
  {:else}
    <div class="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4 md:gap-6">
      {#each tiles as tile (tile.year)}
        <MemoryYearCard {tile} onopen={openYear} onplay={playYear} />
      {/each}
    </div>
  {/if}
</div>
