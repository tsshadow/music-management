<script>
  import { t } from './i18n/index.js';
  import { onMount } from 'svelte';
  import { authParams, currentTrack, playerState, restUrl } from './store.js';
  import TrackList from './TrackList.svelte';
  import { memoriesUrl, memoryCount, memoryHeading, parseMemoryGroups } from './memories.js';
  import { startQueue } from './queue.js';
  import { arrayContinuation } from './listContinuation.js';
  import Skeleton from './loading/Skeleton.svelte';
  import SkeletonRows from './loading/SkeletonRows.svelte';

  const { year, onnavigate } = $props();

  /** How many tracks the page shows before the reader asks for more. */
  const PAGE_SIZE = 50;

  let group = $state(null);
  let isLoading = $state(true);
  let shownCount = $state(PAGE_SIZE);

  const songs = $derived(group?.songs ?? []);
  const visible = $derived(songs.slice(0, shownCount));
  // A row tap queues what is shown; the rest of the year follows as the queue nears its end
  // (docs/designs/list-continuation/), instead of the queue stopping at the first 50.
  const continuation = $derived(arrayContinuation(songs.slice(shownCount), { pageSize: PAGE_SIZE }));
  const heading = $derived(group ? memoryHeading(group) : null);

  // The year's own size as the server counts it, which is what the header says out loud.
  const total = $derived(group ? memoryCount(group) : 0);

  /**
   * Loads one year of today's memories.
   *
   * The page fetches for itself rather than inheriting the overview's data, so that a bookmark or a
   * refresh of /memories/2025 lands on a filled page. Which tracks that is depends on the day: the
   * memories of the 3rd are not the memories of the 4th, and the empty state says so.
   */
  async function loadYear() {
    if (!$authParams) return;
    isLoading = true;
    shownCount = PAGE_SIZE;
    try {
      const response = await fetch(restUrl(memoriesUrl($authParams, { year })));
      if (response.ok) {
        const data = await response.json();
        group = parseMemoryGroups(data).find((candidate) => String(candidate.year) === String(year)) ?? null;
      }
    } catch (e) {
      // A server without the endpoint has no memories rather than an error worth showing.
      console.error('Failed to load memories:', e);
      group = null;
    } finally {
      isLoading = false;
    }
  }

  onMount(loadYear);

  /** Plays the whole year, in the order shown. */
  function playYear() {
    if (songs.length === 0) return;

    startQueue(songs, { name: heading ? $t(heading.key, heading.vars) : String(year) });
    currentTrack.set(songs[0]);
    playerState.update((s) => ({ ...s, playing: true }));
  }
</script>

<div class="flex flex-col gap-6 pb-12">
  <button
    class="self-start bg-transparent border-none text-muma-spotify-text text-[12px] font-bold cursor-pointer uppercase tracking-[0.1em] hover:underline p-0"
    onclick={() => onnavigate('memories')}
  >
    {$t('memories.allYears')}
  </button>

  <header class="flex flex-wrap items-end gap-x-4 gap-y-2">
    <h1 class="text-4xl md:text-6xl font-black m-0">{year}</h1>
    {#if heading}
      <p class="text-muma-spotify-text m-0 pb-1">
        {$t(heading.key, heading.vars)} • {$t('common.trackCount', { count: total })}
      </p>
    {:else if isLoading}
      <!-- The year is known from the route; only the line under it waits. -->
      <Skeleton class="h-4 w-48 mb-2" />
    {/if}
  </header>

  {#if isLoading}
    <SkeletonRows count={10} />
  {:else if songs.length === 0}
    <div class="flex flex-col gap-2">
      <p class="text-white font-bold">{$t('memories.emptyYear', { year })}</p>
      <p class="text-muma-spotify-text">{$t('memories.emptyYearHelp')}</p>
    </div>
  {:else}
    <div>
      <button
        class="bg-brand text-black w-12 h-12 rounded-full flex items-center justify-center shadow-xl hover:scale-105 active:scale-95 transition cursor-pointer border-none"
        onclick={playYear}
        title={$t('common.playAll')}
        aria-label={$t('common.playAll')}
      >
        <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor" aria-hidden="true">
          <path d="M7 6v12l10-6z"></path>
        </svg>
      </button>
    </div>

    <TrackList tracks={visible} {continuation} {onnavigate} />

    {#if shownCount < songs.length}
      <button
        class="self-center bg-transparent border border-white/20 rounded-full px-6 py-2 text-white text-sm font-bold cursor-pointer hover:border-white/60 transition"
        onclick={() => (shownCount += PAGE_SIZE)}
      >
        {$t('common.loadMore')}
      </button>
    {/if}
  {/if}
</div>
