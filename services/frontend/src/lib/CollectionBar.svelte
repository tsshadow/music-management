<script>
  /**
   * The sort/filter header shared by the Genres, Labels, Podcasts and Playlists
   * views.
   *
   * `FilterBar` is the equivalent for the track/album/artist views, but those
   * filter server-side and take a different set of controls; this one drives
   * the purely client-side `queryCollection`. The two are deliberately styled
   * the same so the app still reads as one thing.
   */
  import { t } from './i18n/index.js';
  import { COLLECTION_SORTS, SIZE_THRESHOLDS, sortOption } from './collections.js';

  let {
    type,
    state = $bindable(),
    total = 0,
    shown = 0,
    favoriteCount = 0,
    // Podcasts have no favorites store, so the chip would only ever empty the
    // grid there; a view without favorites hides it instead of showing a control
    // that cannot do anything.
    showFavorites = true,
    // Lineups carry no song counts, so the size chip there would be a control that
    // cannot change the grid; a view without counts hides it rather than showing it.
    showThreshold = true,
    visibilityOptions = [],
    onchange
  } = $props();

  const sorts = $derived(COLLECTION_SORTS[type] || []);

  function notify() {
    if (onchange) onchange(state);
  }

  /**
   * Switching sort key also picks the direction that is useful for it: A-Z for
   * a name, high-to-low for a count or a date. The toggle stays available for
   * anyone who wants the other end of the list.
   */
  function handleSortChange(event) {
    state.sort = event.currentTarget.value;
    state.direction = sortOption(type, state.sort).defaultDirection;
    notify();
  }

  function toggleDirection() {
    state.direction = state.direction === 'asc' ? 'desc' : 'asc';
    notify();
  }

  function setThreshold(id) {
    state.threshold = id;
    notify();
  }

  function setVisibility(id) {
    state.visibility = id;
    notify();
  }

  function toggleFavoritesOnly() {
    state.favoritesOnly = !state.favoritesOnly;
    notify();
  }

  let searchTimeout;
  function handleSearchInput() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(notify, 250);
  }

  const chip =
    'px-3 py-1.5 rounded-full text-[12px] font-bold border transition-colors cursor-pointer whitespace-nowrap';
  const chipOn = 'bg-brand text-black border-brand';
  const chipOff = 'bg-[#282828] text-[#b3b3b3] border-transparent hover:text-white hover:bg-[#333]';
</script>

<div class="flex flex-col gap-4 mb-6 bg-[#181818] p-3 md:p-4 rounded-lg">
  <div class="flex flex-col md:flex-row gap-3 md:items-center">
    <input
      type="text"
      placeholder={$t('common.searchPlaceholder')}
      aria-label={$t('collection.searchLabel')}
      class="flex-1 min-w-0 bg-[#282828] text-white border-none px-4 py-2 rounded-[20px] text-sm focus:outline focus:outline-1 focus:outline-brand focus:bg-[#333]"
      bind:value={state.search}
      oninput={handleSearchInput}
    />

    <div class="flex items-center gap-2 shrink-0">
      <label for="{type}-sort" class="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-wider">{$t('filter.sortBy')}</label>
      <select
        id="{type}-sort"
        class="bg-[#282828] text-white border-none px-3 py-1.5 rounded text-sm cursor-pointer focus:outline focus:outline-1 focus:outline-brand"
        value={state.sort}
        onchange={handleSortChange}
      >
        {#each sorts as option (option.id)}
          <option value={option.id}>{$t(option.labelKey)}</option>
        {/each}
      </select>
      <button
        type="button"
        class="bg-[#282828] text-[#b3b3b3] p-1.5 rounded hover:bg-[#333] hover:text-white transition-colors focus:outline focus:outline-1 focus:outline-brand cursor-pointer"
        onclick={toggleDirection}
        title={state.direction === 'asc' ? $t('collection.sortedAscending') : $t('collection.sortedDescending')}
        aria-label={$t('collection.reverseOrder')}
      >
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          {#if state.direction === 'asc'}
            <path d="M12 19V5M5 12l7-7 7 7"></path>
          {:else}
            <path d="M12 5v14M5 12l7 7 7-7"></path>
          {/if}
        </svg>
      </button>
    </div>
  </div>

  <div class="flex flex-wrap items-center gap-2">
    {#if showFavorites}
    <button
      type="button"
      class="{chip} {state.favoritesOnly ? chipOn : chipOff} flex items-center gap-1.5"
      onclick={toggleFavoritesOnly}
      aria-pressed={state.favoritesOnly}
    >
      <svg viewBox="0 0 24 24" width="13" height="13" fill={state.favoritesOnly ? 'currentColor' : 'none'} stroke="currentColor" stroke-width="2">
        <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"></path>
      </svg>
      {$t('collection.favoritesFilter', { count: favoriteCount })}
    </button>
    {/if}

    {#if visibilityOptions.length > 0}
      <span class="w-px h-5 bg-white/10 mx-1" aria-hidden="true"></span>
      {#each visibilityOptions as option (option.id)}
        <button
          type="button"
          class="{chip} {state.visibility === option.id ? chipOn : chipOff}"
          onclick={() => setVisibility(option.id)}
          aria-pressed={state.visibility === option.id}
        >{$t(option.labelKey)}</button>
      {/each}
    {/if}

    {#if type !== 'playlists' && showThreshold}
      <span class="w-px h-5 bg-white/10 mx-1" aria-hidden="true"></span>
      <span class="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-wider">{$t('collection.minimum')}</span>
      {#each SIZE_THRESHOLDS as option (option.id)}
        <button
          type="button"
          class="{chip} {state.threshold === option.id ? chipOn : chipOff}"
          onclick={() => setThreshold(option.id)}
          aria-pressed={state.threshold === option.id}
        >{option.labelKey ? $t(option.labelKey) : option.label}</button>
      {/each}
    {/if}

    <span class="ml-auto text-[12px] text-[#b3b3b3] tabular-nums">
      {shown === total ? total : $t('collection.shownOfTotal', { shown, total })}
    </span>
  </div>
</div>
