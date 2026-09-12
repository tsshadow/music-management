<script>
  /**
   * One browse page's card grid: heading, sort/filter bar, and a grid of cards.
   *
   * Genres, Labels, Podcasts, Festivals, Years and Lineups differ only in the icon on
   * the card, whether the card carries a count line, and whether the collection can be
   * favorited. Everything else -- the loading state, the two kinds of empty, the
   * client-side query -- was written once per page before this component existed.
   *
   * Playlists deliberately stay outside: their cards show a duration and an owner and
   * their bar carries a visibility filter, which is a different card, not a variation.
   */
  import { t } from './i18n/index.js';
  import CollectionBar from './CollectionBar.svelte';
  import { defaultCollectionState, queryCollection } from './collections.js';

  let {
    type,
    title,
    items = [],
    state = $bindable(),
    loading = false,
    favorites = [],
    onfavorite = null,
    favoriteAriaLabel = null,
    emptyText,
    emptyHint = null,
    onselect,
    context = {}
  } = $props();

  /**
   * What a card shows, per collection.
   *
   * `count` picks the line under the name: 'tracks' adds the album count when the
   * server sent one, 'episodes' is the podcast wording, and 'none' is for a
   * collection the server cannot count at all.
   */
  const CARDS = {
    genres: { count: 'tracks', icon: 'M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z' },
    labels: { count: 'tracks', icon: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 15c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z' },
    podcasts: { count: 'episodes', icon: 'M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5-3c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-2.08c3.39-.49 6-3.39 6-6.92h-2z' },
    festivals: { count: 'tracks', icon: 'M12 2L2 22h20L12 2zm0 4.8L18.1 20H5.9L12 6.8z' },
    years: { count: 'tracks', icon: 'M19 4h-1V2h-2v2H8V2H6v2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 16H5V10h14v10zM5 8V6h14v2H5z' },
    lineups: { count: 'none', icon: 'M4 6h16v2H4V6zm0 5h16v2H4v-2zm0 5h10v2H4v-2z' }
  };

  const card = $derived(CARDS[type] ?? CARDS.genres);
  const visible = $derived(queryCollection(items, type, state, { favorites, ...context }));

  function clearFilters() {
    state = defaultCollectionState(type);
  }

  function open(item) {
    onselect(item);
  }
</script>

<div class="flex flex-col gap-4 mb-6">
  <h2 class="text-2xl font-bold m-0">{title}</h2>
  <CollectionBar
    {type}
    bind:state
    total={items.length}
    shown={visible.length}
    favoriteCount={favorites.length}
    showFavorites={onfavorite !== null}
    showThreshold={card.count !== 'none'}
  />
</div>

{#if loading && items.length === 0}
  <p>{$t('common.loading')}</p>
{:else if items.length === 0}
  <div class="text-[#b3b3b3]">
    <p>{emptyText}</p>
    {#if emptyHint}
      <p class="text-sm opacity-60 mt-2">{emptyHint}</p>
    {/if}
  </div>
{:else if visible.length === 0}
  <div class="text-[#b3b3b3] p-12 text-center border border-white/5 rounded-xl bg-white/5">
    <p class="text-xl font-bold mb-2 text-white">{$t('collection.noMatches')}</p>
    <p class="text-sm opacity-60 mb-4">{$t('collection.noMatchesHelp')}</p>
    <button
      class="bg-transparent border border-[#727272] text-white px-6 py-2 rounded-[24px] font-bold cursor-pointer transition-all hover:border-white hover:scale-[1.04]"
      onclick={clearFilters}
    >{$t('collection.clearFilters')}</button>
  </div>
{:else}
  <div class="grid grid-cols-3 gap-3 md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] md:gap-6">
    {#each visible as item (item.value)}
      <div
        role="button"
        tabindex="0"
        class="bg-[#181818] p-3 md:p-6 rounded-lg flex flex-col items-center justify-center gap-1.5 md:gap-3 cursor-pointer transition-colors hover:bg-[#282828] aspect-square relative group"
        onclick={() => open(item)}
        onkeydown={(e) => e.key === 'Enter' && open(item)}
      >
        {#if onfavorite}
          <button
            class="absolute top-3 right-3 p-2 bg-black/40 rounded-full text-brand transition-all hover:scale-110 active:scale-95 {favorites.includes(item.value) ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}"
            onclick={(e) => { e.stopPropagation(); onfavorite(item.value); }}
            aria-label={favoriteAriaLabel ?? $t('dashboard.toggleFavorite')}
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill={favorites.includes(item.value) ? "currentColor" : "none"} stroke="currentColor" stroke-width="2">
              <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"></path>
            </svg>
          </button>
        {/if}
        <!-- The colour is MuMa's, sent alongside the genre so the app draws the same one.
             Without it the mark keeps the brand accent it always had. An inline style rather
             than a class: the value is a hex from the server, and Tailwind can only compile
             classes it can see. -->
        <div
          class="w-10 h-10 md:w-16 md:h-16 rounded-full flex items-center justify-center text-black mb-1 md:mb-2 shadow-lg {item.tint ? '' : 'bg-brand'}"
          style={item.tint ? `background-color: ${item.tint}` : undefined}
        >
          <svg viewBox="0 0 24 24" class="w-5 h-5 md:w-8 md:h-8" fill="currentColor">
            <path d={card.icon}></path>
          </svg>
        </div>
        <span class="font-bold text-center break-words w-full">
          {#if item.isAll}
            {$t('collection.allOfLineup', { name: item.label })}
          {:else}
            {item.label ?? item.value}
          {/if}
        </span>
        {#if item.path}
          <!-- Only a search hit carries a path: it says which edition or stage it came
               from, which the label alone ('RED') does not. -->
          <span class="text-xs text-[#b3b3b3] text-center break-words w-full">{item.path}</span>
        {/if}
        {#if card.count === 'episodes'}
          <span class="text-xs text-[#b3b3b3] text-center">
            {$t('collection.episodeCount', { count: Number(item.songCount) || 0 })}
          </span>
        {:else if card.count === 'tracks' && item.songCount !== undefined}
          <!-- Older servers answer getRecordLabels without any counts; the card simply
               leaves the line out rather than showing "0 nummers". -->
          <span class="text-xs text-[#b3b3b3] text-center">
            {$t('common.trackCount', { count: Number(item.songCount) || 0 })}
            {#if Number(item.albumCount) > 0}
              &middot; {$t('collection.albumCount', { count: Number(item.albumCount) })}
            {/if}
          </span>
        {/if}
      </div>
    {/each}
  </div>
{/if}
