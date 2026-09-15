<script>
  /**
   * One row on the Home screen: a heading with a "show all" link, and the tracks under it.
   *
   * Desktop keeps the two-column-per-row card grid it always had. On a phone that grid put one
   * row of cards per screen and forced endless scrolling to see four sections, so there it becomes
   * a single horizontally-scrolling shelf instead -- the same layout Spotify uses for "Daily Mix",
   * "Made For You" and so on. `isMobile` drives the split rather than a `md:` breakpoint alone,
   * matching how the rest of the app already tells a phone from a desktop browser window
   * (see TrackList.svelte, Toaster.svelte).
   */
  import { isMobile } from './store.js';
  import TrackCard from './TrackCard.svelte';

  const { title, tracks = [], noTracksText = '', showAllLabel = '', onshowall, onnavigate } = $props();
</script>

<section class="flex flex-col {$isMobile ? 'gap-3' : 'gap-4'}">
  <div class="flex justify-between items-end mb-4">
    <h2 class="{$isMobile ? 'text-xl' : 'text-2xl'} font-bold m-0">{title}</h2>
    <button
      class="bg-transparent border-none text-[#b3b3b3] text-[12px] font-bold cursor-pointer uppercase tracking-[0.1em] hover:underline"
      onclick={onshowall}
    >{showAllLabel}</button>
  </div>
  <div
    class={$isMobile
      ? 'flex gap-3 overflow-x-auto snap-x snap-mandatory scrollbar-hide -mx-4 px-4 pb-1'
      : 'grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4 md:gap-6'}
  >
    {#each tracks as track (track.id)}
      <div class={$isMobile ? 'w-[140px] shrink-0 snap-start' : ''}>
        <TrackCard {track} {onnavigate} />
      </div>
    {/each}
    {#if tracks.length === 0}
      <p class="text-[#b3b3b3] col-span-full">{noTracksText}</p>
    {/if}
  </div>
</section>
