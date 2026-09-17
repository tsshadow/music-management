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
  import TrackRowCompact from './TrackRowCompact.svelte';

  /**
   * `layout="rows"` swaps the card grid/shelf for a vertical list of `TrackRowCompact` rows --
   * PhoneHome's "recently released"/"recently added" shelves use it, where a wall of mostly-
   * placeholder square cards read worse than a plain list. `"cards"` (the default) keeps every
   * existing caller's look exactly as it was.
   */
  const { title, tracks = [], noTracksText = '', showAllLabel = '', layout = 'cards', onshowall, onnavigate } = $props();
</script>

<section class="flex flex-col {$isMobile ? 'gap-3' : 'gap-4'}">
  <div class="flex justify-between items-end mb-4">
    <h2 class="{$isMobile ? 'text-xl' : 'text-2xl'} font-bold m-0">{title}</h2>
    <button
      class="bg-transparent border-none text-[#b3b3b3] text-[13px] font-bold cursor-pointer hover:underline"
      onclick={onshowall}
    >{showAllLabel}</button>
  </div>
  {#if layout === 'rows'}
    <div class="flex flex-col gap-1">
      {#each tracks as track (track.id)}
        <TrackRowCompact {track} {onnavigate} />
      {/each}
      {#if tracks.length === 0}
        <p class="text-[#b3b3b3]">{noTracksText}</p>
      {/if}
    </div>
  {:else}
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
  {/if}
</section>
