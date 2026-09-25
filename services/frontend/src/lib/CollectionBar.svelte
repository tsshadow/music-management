<script>
  /**
   * The sort/filter header shared by the Genres, Labels, Podcasts and Playlists
   * views.
   *
   * `FilterBar` is the equivalent for the track/album/artist views, but those
   * filter server-side and take a different set of controls; this one drives
   * the purely client-side `queryCollection`. The two are deliberately styled
   * the same so the app still reads as one thing, including on the phone: the
   * mobile branch below mirrors FilterBar's chip-row-plus-bottom-sheet
   * approach rather than inventing a second pattern.
   */
  import { t } from './i18n/index.js';
  import { COLLECTION_SORTS, SIZE_THRESHOLDS, sortOption } from './collections.js';
  import { isMobile } from './store.js';
  import BottomSheet from './BottomSheet.svelte';

  // The prop is renamed to `collectionState` on arrival: Svelte's compiler
  // treats a `$`-prefixed identifier as a store subscription, and a local
  // binding literally called `state` makes it read every `$state(...)` rune
  // below as "subscribe to a store named state" instead. The prop's own name
  // (what `CollectionGrid`/`Dashboard` bind to) is unaffected.
  let {
    type,
    state: collectionState = $bindable(),
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

  // The noun for the count line ("296 playlists"): every type already has a
  // plural in the main navigation, so this borrows it rather than adding a
  // parallel set of translations.
  const TYPE_LABEL_KEYS = {
    genres: 'nav.genres',
    labels: 'nav.labels',
    podcasts: 'nav.podcasts',
    festivals: 'nav.festivals',
    years: 'nav.years',
    lineups: 'nav.lineups',
    playlists: 'nav.playlists'
  };
  const typeLabel = $derived($t(TYPE_LABEL_KEYS[type] ?? 'nav.genres'));
  const countLabel = $derived(
    shown === total ? `${total} ${typeLabel}` : `${$t('collection.shownOfTotal', { shown, total })} ${typeLabel}`
  );

  let mobileSearchOpen = $state(false);
  let sortSheetOpen = $state(false);
  let mobileSearchInput = $state(null);

  $effect(() => {
    if (mobileSearchOpen) mobileSearchInput?.focus();
  });

  function notify() {
    if (onchange) onchange(collectionState);
  }

  /**
   * Switching sort key also picks the direction that is useful for it: A-Z for
   * a name, high-to-low for a count or a date. The toggle stays available for
   * anyone who wants the other end of the list.
   */
  function handleSortChange(event) {
    collectionState.sort = event.currentTarget.value;
    collectionState.direction = sortOption(type, collectionState.sort).defaultDirection;
    notify();
  }

  function toggleDirection() {
    collectionState.direction = collectionState.direction === 'asc' ? 'desc' : 'asc';
    notify();
  }

  function setThreshold(id) {
    collectionState.threshold = id;
    notify();
  }

  function setVisibility(id) {
    collectionState.visibility = id;
    notify();
  }

  function toggleFavoritesOnly() {
    collectionState.favoritesOnly = !collectionState.favoritesOnly;
    notify();
  }

  function selectSort(id) {
    collectionState.sort = id;
    collectionState.direction = sortOption(type, id).defaultDirection;
    sortSheetOpen = false;
    notify();
  }

  function selectDirection(direction) {
    collectionState.direction = direction;
    sortSheetOpen = false;
    notify();
  }

  let searchTimeout;
  function handleSearchInput() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(notify, 250);
  }

  const chip =
    'px-3 py-1.5 rounded-full text-[12px] font-bold border transition-colors cursor-pointer whitespace-nowrap shrink-0';
  const chipOn = 'bg-brand text-black border-brand';
  const chipOff = 'bg-muma-spotify-light text-muma-spotify-text border-transparent hover:text-white hover:bg-muma-spotify-hover';

  const currentSortLabel = $derived($t(sortOption(type, collectionState?.sort)?.labelKey ?? 'filter.sortBy'));
</script>

{#snippet sheetOption(label, selected, onSelect)}
  <button
    type="button"
    class="w-full flex items-center justify-between gap-3 px-4 py-3 text-left bg-transparent border-none cursor-pointer text-white hover:bg-white/5 {selected ? 'text-brand' : ''}"
    role="option"
    aria-selected={selected}
    onclick={onSelect}
  >
    <span class="truncate">{label}</span>
    {#if selected}
      <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" class="shrink-0">
        <path d="M9 16.2L4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z"></path>
      </svg>
    {/if}
  </button>
{/snippet}

{#if $isMobile}
  <div class="flex flex-col gap-2 mb-4" data-testid="mobile-collection-bar">
    {#if mobileSearchOpen}
      <div class="flex items-center gap-2 bg-muma-spotify-light rounded-[20px] px-3 py-2">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" class="text-muma-spotify-text shrink-0">
          <circle cx="11" cy="11" r="7"></circle>
          <path d="M21 21l-4.3-4.3"></path>
        </svg>
        <input
          bind:this={mobileSearchInput}
          type="text"
          placeholder={$t('common.searchPlaceholder')}
          aria-label={$t('collection.searchLabel')}
          class="flex-1 min-w-0 bg-transparent text-white border-none text-sm focus:outline-none"
          bind:value={collectionState.search}
          oninput={handleSearchInput}
        />
        <button
          type="button"
          class="bg-transparent border-none text-muma-spotify-text hover:text-white cursor-pointer p-0.5"
          aria-label={$t('filter.searchClose')}
          onclick={() => (mobileSearchOpen = false)}
        >
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <path d="M18.3 5.71a.996.996 0 00-1.41 0L12 10.59 7.11 5.7a.996.996 0 10-1.41 1.41L10.59 12 5.7 16.89a.996.996 0 101.41 1.41L12 13.41l4.89 4.89a.996.996 0 101.41-1.41L13.41 12l4.89-4.89c.38-.38.38-1.02 0-1.4z"></path>
          </svg>
        </button>
      </div>
    {/if}

    <div
      class="flex items-center gap-2 overflow-x-auto scrollbar-hide"
      role="group"
      aria-label={$t('filter.filtersGroup')}
      data-testid="mobile-collection-chips"
    >
      {#if !mobileSearchOpen}
        <button
          type="button"
          class="flex items-center justify-center w-9 h-9 rounded-full shrink-0 {collectionState.search ? chipOn : chipOff}"
          aria-label={$t('filter.searchOpen')}
          data-testid="chip-search"
          onclick={() => (mobileSearchOpen = true)}
        >
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="7"></circle>
            <path d="M21 21l-4.3-4.3"></path>
          </svg>
        </button>
      {/if}

      {#if showFavorites}
        <button
          type="button"
          class="{chip} {collectionState.favoritesOnly ? chipOn : chipOff} flex items-center gap-1.5"
          onclick={toggleFavoritesOnly}
          aria-pressed={collectionState.favoritesOnly}
        >
          <svg viewBox="0 0 24 24" width="13" height="13" fill={collectionState.favoritesOnly ? 'currentColor' : 'none'} stroke="currentColor" stroke-width="2">
            <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"></path>
          </svg>
          {$t('collection.favoritesFilter', { count: favoriteCount })}
        </button>
      {/if}

      {#each visibilityOptions as option (option.id)}
        <button
          type="button"
          class="{chip} {collectionState.visibility === option.id ? chipOn : chipOff}"
          onclick={() => setVisibility(option.id)}
          aria-pressed={collectionState.visibility === option.id}
        >{$t(option.labelKey)}</button>
      {/each}

      {#if type !== 'playlists' && showThreshold}
        {#each SIZE_THRESHOLDS as option (option.id)}
          <button
            type="button"
            class="{chip} {collectionState.threshold === option.id ? chipOn : chipOff}"
            onclick={() => setThreshold(option.id)}
            aria-pressed={collectionState.threshold === option.id}
          >{option.labelKey ? $t(option.labelKey) : option.label}</button>
        {/each}
      {/if}

      <div class="flex items-center rounded-full border shrink-0 bg-brand text-black border-brand">
        <button
          type="button"
          class="pl-3 pr-3 py-1.5 text-[13px] font-bold bg-transparent border-none cursor-pointer flex items-center gap-1"
          data-testid="chip-sort"
          onclick={() => (sortSheetOpen = true)}
        >
          <span class="max-w-[130px] truncate">{currentSortLabel}</span>
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" class="shrink-0">
            <path d="M6 9l6 6 6-6"></path>
          </svg>
        </button>
      </div>
    </div>

    <span class="text-[12px] text-muma-spotify-text tabular-nums px-1" data-testid="mobile-collection-count">{countLabel}</span>
  </div>

  {#if sortSheetOpen}
    <BottomSheet title={$t('filter.sortBy')} onclose={() => (sortSheetOpen = false)}>
      <div role="listbox" aria-label={$t('filter.sortBy')}>
        {#each sorts as option (option.id)}
          {@render sheetOption($t(option.labelKey), collectionState.sort === option.id, () => selectSort(option.id))}
        {/each}
      </div>
      <div class="border-t border-white/10 mt-1 pt-1" role="listbox" aria-label={$t('collection.reverseOrder')}>
        {@render sheetOption($t('collection.ascending'), collectionState.direction === 'asc', () => selectDirection('asc'))}
        {@render sheetOption($t('collection.descending'), collectionState.direction === 'desc', () => selectDirection('desc'))}
      </div>
    </BottomSheet>
  {/if}
{:else}
  <div class="flex flex-col gap-4 mb-6 bg-muma-spotify-panel p-3 md:p-4 rounded-lg">
    <div class="flex flex-col md:flex-row gap-3 md:items-center">
      <input
        type="text"
        placeholder={$t('common.searchPlaceholder')}
        aria-label={$t('collection.searchLabel')}
        class="flex-1 min-w-0 bg-muma-spotify-light text-white border-none px-4 py-2 rounded-[20px] text-sm focus:outline focus:outline-1 focus:outline-brand focus:bg-muma-spotify-hover"
        bind:value={collectionState.search}
        oninput={handleSearchInput}
      />

      <div class="flex items-center gap-2 shrink-0">
        <label for="{type}-sort" class="text-[11px] font-bold text-muma-spotify-text uppercase tracking-wider">{$t('filter.sortBy')}</label>
        <select
          id="{type}-sort"
          class="bg-muma-spotify-light text-white border-none px-3 py-1.5 rounded text-sm cursor-pointer focus:outline focus:outline-1 focus:outline-brand"
          value={collectionState.sort}
          onchange={handleSortChange}
        >
          {#each sorts as option (option.id)}
            <option value={option.id}>{$t(option.labelKey)}</option>
          {/each}
        </select>
        <button
          type="button"
          class="bg-muma-spotify-light text-muma-spotify-text p-1.5 rounded hover:bg-muma-spotify-hover hover:text-white transition-colors focus:outline focus:outline-1 focus:outline-brand cursor-pointer"
          onclick={toggleDirection}
          title={collectionState.direction === 'asc' ? $t('collection.sortedAscending') : $t('collection.sortedDescending')}
          aria-label={$t('collection.reverseOrder')}
        >
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            {#if collectionState.direction === 'asc'}
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
        class="{chip} {collectionState.favoritesOnly ? chipOn : chipOff} flex items-center gap-1.5"
        onclick={toggleFavoritesOnly}
        aria-pressed={collectionState.favoritesOnly}
      >
        <svg viewBox="0 0 24 24" width="13" height="13" fill={collectionState.favoritesOnly ? 'currentColor' : 'none'} stroke="currentColor" stroke-width="2">
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
            class="{chip} {collectionState.visibility === option.id ? chipOn : chipOff}"
            onclick={() => setVisibility(option.id)}
            aria-pressed={collectionState.visibility === option.id}
          >{$t(option.labelKey)}</button>
        {/each}
      {/if}

      {#if type !== 'playlists' && showThreshold}
        <span class="w-px h-5 bg-white/10 mx-1" aria-hidden="true"></span>
        <span class="text-[11px] font-bold text-muma-spotify-text uppercase tracking-wider">{$t('collection.minimum')}</span>
        {#each SIZE_THRESHOLDS as option (option.id)}
          <button
            type="button"
            class="{chip} {collectionState.threshold === option.id ? chipOn : chipOff}"
            onclick={() => setThreshold(option.id)}
            aria-pressed={collectionState.threshold === option.id}
          >{option.labelKey ? $t(option.labelKey) : option.label}</button>
        {/each}
      {/if}

      <span class="ml-auto text-[12px] text-muma-spotify-text tabular-nums">
        {shown === total ? total : $t('collection.shownOfTotal', { shown, total })}
      </span>
    </div>
  </div>
{/if}
