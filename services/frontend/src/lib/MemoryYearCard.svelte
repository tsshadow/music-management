<script>
  import { t } from './i18n/index.js';
  import { authParams } from './store.js';
  import { memoryHeading } from './memories.js';

  const { tile, onopen, onplay } = $props();

  const heading = $derived(memoryHeading(tile));

  // Four covers make a mosaic; anything less is shown as one square, because a 2x2 grid with a
  // hole in it reads as a broken image rather than as a collage.
  const mosaic = $derived(tile.covers.length >= 4);
  const shown = $derived(mosaic ? tile.covers.slice(0, 4) : tile.covers.slice(0, 1));

  /**
   * The cover art URL for one id.
   *
   * @param {string} id - The coverArt id.
   * @returns {string} The request URL.
   */
  function coverUrl(id) {
    return `/rest/getCoverArt?id=${id}&size=300&${$authParams}`;
  }
</script>

<div
  class="group relative flex flex-col bg-[#181818] rounded-lg overflow-hidden hover:bg-[#282828] transition-all"
>
  <button
    class="text-left border-none bg-transparent p-0 cursor-pointer"
    onclick={() => onopen(tile.year)}
    aria-label={$t('memories.openYear', { year: tile.year })}
  >
    <div class="relative aspect-square">
      {#if shown.length === 0}
        <img src="/images/spotify-fallback.svg" alt="" class="w-full h-full object-cover" />
      {:else}
        <div class="grid {mosaic ? 'grid-cols-2 grid-rows-2' : 'grid-cols-1'} w-full h-full">
          <!-- Keyed by position, not by cover id: the same sleeve can legitimately appear twice, and
               a duplicate key is a render error that blanks the whole screen rather than one tile. -->
          {#each shown as cover, position (position)}
            <img
              src={coverUrl(cover)}
              alt=""
              loading="lazy"
              class="w-full h-full object-cover"
              onerror={(e) => (e.target.src = '/images/spotify-fallback.svg')}
            />
          {/each}
        </div>
      {/if}

      <!-- The scrim keeps the year legible whatever the covers happen to be. -->
      <div class="absolute inset-0 bg-gradient-to-t from-black/85 via-black/20 to-transparent"></div>
      <div class="absolute left-4 right-4 bottom-3">
        <span class="block text-4xl md:text-5xl font-black leading-none text-white drop-shadow-lg">
          {tile.year}
        </span>
        <span class="block text-xs text-white/70 mt-1 truncate">
          {$t(heading.key, heading.vars)}
        </span>
      </div>
    </div>

    <ol class="list-none m-0 px-4 pt-4 pb-2 flex flex-col gap-1">
      {#each tile.top as song, index (song.id)}
        <li class="flex gap-2 text-sm min-w-0">
          <span class="text-[#b3b3b3] tabular-nums w-3 shrink-0">{index + 1}</span>
          <span class="text-white truncate">{song.title}</span>
        </li>
      {/each}
    </ol>
  </button>

  <div class="flex items-center gap-3 px-4 pb-4 mt-auto">
    <button
      class="bg-brand text-black w-9 h-9 rounded-full flex items-center justify-center shadow-lg hover:scale-105 active:scale-95 transition cursor-pointer border-none shrink-0"
      onclick={() => onplay(tile.year)}
      title={$t('common.playAll')}
      aria-label={$t('common.playAll')}
    >
      <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
        <path d="M7 6v12l10-6z"></path>
      </svg>
    </button>
    <span class="text-sm text-[#b3b3b3] truncate">
      {$t('common.trackCount', { count: tile.count })}
    </span>
  </div>
</div>
