<script>
  import { t } from './i18n/index.js';

  import { authParams, visibleSortOptions, allSortOptions, isMobile } from './store.js';
  import { listOf, subsonicJson } from './subsonic.js';
  import { QUALITY_FLOORS, QUALITY_LABEL_KEYS } from './quality.js';
  import BottomSheet from './BottomSheet.svelte';

  let {
    genre = $bindable(''),
    sort = $bindable('recent'),
    year = $bindable(''),
    search = $bindable(''),
    minRating = $bindable('0'),
    includeUnrated = $bindable(true),
    // A floor on the QUALITY cluster, '' for no floor. Rarely touched -- it exists for
    // trying a new car stereo on lossless files -- so it sits after the rating.
    minQuality = $bindable(''),
    role = $bindable('all'),
    view = 'songs',
    showGenre = true,
    // A year page is already a year filter; offering the picker there lets the two
    // disagree, with the route silently losing.
    showYear = true,
    onchange
  } = $props();

  let genres = $state([]);
  let years = $state([]);

  // Phone-only: which bottom sheet is open, and whether the compact search
  // chip has expanded into a real input. Both start closed -- the whole
  // point of the chip row is that nothing here takes vertical space until a
  // tap asks for it.
  let openSheet = $state(null);
  let mobileSearchOpen = $state(false);
  let mobileSearchInput = $state(null);

  $effect(() => {
    if (mobileSearchOpen) mobileSearchInput?.focus();
  });

  const roles = [
    { value: 'all', labelKey: 'filter.roles.all' },
    { value: 'release', labelKey: 'filter.roles.release' },
    { value: 'track', labelKey: 'filter.roles.track' },
    { value: 'composer', labelKey: 'filter.roles.composer' },
    { value: 'conductor', labelKey: 'filter.roles.conductor' },
    { value: 'lyricist', labelKey: 'filter.roles.lyricist' },
    { value: 'mixer', labelKey: 'filter.roles.mixer' },
    { value: 'performer', labelKey: 'filter.roles.performer' },
    { value: 'producer', labelKey: 'filter.roles.producer' },
    { value: 'remixer', labelKey: 'filter.roles.remixer' },
    { value: 'writer', labelKey: 'filter.roles.writer' }
  ];

  /**
   * Fetches the list of all available genres from the server.
   */
  async function loadGenres() {
    if (!$authParams) return;
    try {
        genres = listOf(await subsonicJson('getGenres'), 'genres.genre')
            .filter(g => Number(g.songCount) >= 10)
            .sort((a, b) => a.value.localeCompare(b.value));
    } catch (e) {
        console.error("Failed to fetch genres:", e);
    }
  }

  /**
   * Fetches the list of all available release years from the server.
   */
  async function loadYears() {
    if (!$authParams) return;
    try {
        years = listOf(await subsonicJson('getYears'), 'years.year')
            .sort((a, b) => b.value.localeCompare(a.value));
    } catch (e) {
        console.error("Failed to fetch years:", e);
    }
  }

  $effect(() => {
    if ($authParams) {
      void Promise.all([loadGenres(), loadYears()]);
    }
  });

  /**
   * Notifies the parent component of filter/sort changes.
   */
  function handleChange() {
    if (onchange) onchange({ genre, sort, year, search, role, minRating, includeUnrated, minQuality });
  }

  let searchTimeout;
  /**
   * Handles search input with a debounced notification to the parent.
   */
  function handleSearchInput() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(handleChange, 500);
  }

  // --- Phone chip row: same stores and the same handleChange, just picked
  // from a bottom sheet instead of a <select>. ---

  const currentSortLabel = $derived(
    $t((allSortOptions[view] || []).find((o) => o.id === sort)?.labelKey ?? 'filter.sortBy')
  );
  const currentRoleLabel = $derived(
    role === 'all' ? '' : $t(roles.find((r) => r.value === role)?.labelKey ?? 'filter.roles.all')
  );
  const currentRatingLabel = $derived(
    minRating === '0' || !minRating
      ? ''
      : Number(minRating) >= 5
        ? $t('filter.starsExactly', { count: 5 })
        : $t('filter.starsMin', { count: Number(minRating) })
  );
  const unratedActive = $derived(!includeUnrated);
  const currentQualityLabel = $derived(minQuality ? $t(QUALITY_LABEL_KEYS[minQuality]) : '');

  function selectGenre(value) {
    genre = value;
    openSheet = null;
    handleChange();
  }
  function selectYear(value) {
    year = value;
    openSheet = null;
    handleChange();
  }
  function selectRole(value) {
    role = value;
    openSheet = null;
    handleChange();
  }
  function selectRating(value) {
    minRating = value;
    openSheet = null;
    handleChange();
  }
  function selectQuality(value) {
    minQuality = value;
    openSheet = null;
    handleChange();
  }
  function selectSort(value) {
    sort = value;
    openSheet = null;
    handleChange();
  }
  function toggleUnrated() {
    includeUnrated = !includeUnrated;
    handleChange();
  }
  function clearGenre() {
    genre = '';
    handleChange();
  }
  function clearYear() {
    year = '';
    handleChange();
  }
  function clearRole() {
    role = 'all';
    handleChange();
  }
  function clearRating() {
    minRating = '0';
    handleChange();
  }
  function clearQuality() {
    minQuality = '';
    handleChange();
  }

  const chipBase =
    'px-3 py-1.5 rounded-full text-[13px] font-bold border transition-colors cursor-pointer whitespace-nowrap shrink-0';
  const chipOn = 'bg-brand text-black border-brand';
  const chipOff = 'bg-[#282828] text-[#b3b3b3] border-transparent hover:text-white hover:bg-[#333]';
</script>

{#snippet chevron()}
  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" class="shrink-0">
    <path d="M6 9l6 6 6-6"></path>
  </svg>
{/snippet}

{#snippet filterChip(id, label, activeLabel, onOpen, onClear)}
  <div
    class="flex items-center rounded-full border shrink-0 transition-colors {activeLabel ? chipOn : chipOff}"
  >
    <button
      type="button"
      class="pl-3 {activeLabel ? 'pr-1.5' : 'pr-3'} py-1.5 text-[13px] font-bold bg-transparent border-none cursor-pointer flex items-center gap-1"
      aria-haspopup="dialog"
      data-testid="chip-{id}"
      onclick={onOpen}
    >
      <span class="max-w-[110px] truncate">{activeLabel || label}</span>
      {@render chevron()}
    </button>
    {#if activeLabel && onClear}
      <button
        type="button"
        class="pr-2.5 pl-0.5 py-1.5 bg-transparent border-none cursor-pointer opacity-90 hover:opacity-100"
        aria-label={$t('filter.clearFilter', { name: activeLabel })}
        onclick={onClear}
      >
        <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
          <path d="M18.3 5.71a.996.996 0 00-1.41 0L12 10.59 7.11 5.7a.996.996 0 10-1.41 1.41L10.59 12 5.7 16.89a.996.996 0 101.41 1.41L12 13.41l4.89 4.89a.996.996 0 101.41-1.41L13.41 12l4.89-4.89c.38-.38.38-1.02 0-1.4z"></path>
        </svg>
      </button>
    {/if}
  </div>
{/snippet}

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
  <div class="flex flex-col gap-2 mb-4" data-testid="mobile-filter-bar">
    {#if mobileSearchOpen}
      <div class="flex items-center gap-2 bg-[#282828] rounded-[20px] px-3 py-2">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" class="text-[#b3b3b3] shrink-0">
          <circle cx="11" cy="11" r="7"></circle>
          <path d="M21 21l-4.3-4.3"></path>
        </svg>
        <input
          bind:this={mobileSearchInput}
          type="text"
          placeholder={$t('common.searchPlaceholder')}
          aria-label={$t('collection.searchLabel')}
          class="flex-1 min-w-0 bg-transparent text-white border-none text-sm focus:outline-none"
          bind:value={search}
          oninput={handleSearchInput}
        />
        <button
          type="button"
          class="bg-transparent border-none text-[#b3b3b3] hover:text-white cursor-pointer p-0.5"
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
      data-testid="mobile-filter-chips"
    >
      {#if !mobileSearchOpen}
        <button
          type="button"
          class="flex items-center justify-center w-9 h-9 rounded-full shrink-0 {search ? chipOn : chipOff}"
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

      {#if (view === 'songs' || view === 'albums') && showGenre}
        {@render filterChip('genre', $t('filter.genre'), genre, () => (openSheet = 'genre'), clearGenre)}
      {/if}

      {#if view === 'songs' && showYear}
        {@render filterChip('year', $t('filter.year'), year, () => (openSheet = 'year'), clearYear)}
      {/if}

      {#if view === 'artists'}
        {@render filterChip('role', $t('filter.role'), currentRoleLabel, () => (openSheet = 'role'), clearRole)}
      {/if}

      {#if view === 'songs'}
        {@render filterChip('rating', $t('filter.rating'), currentRatingLabel, () => (openSheet = 'rating'), clearRating)}
        {@render filterChip('quality', $t('filter.quality.label'), currentQualityLabel, () => (openSheet = 'quality'), clearQuality)}
      {/if}

      {@render filterChip('sort', $t('filter.sortBy'), currentSortLabel, () => (openSheet = 'sort'), null)}

      {#if view === 'songs'}
        <button
          type="button"
          class="{chipBase} {unratedActive ? chipOn : chipOff}"
          aria-pressed={unratedActive}
          data-testid="chip-unrated"
          onclick={toggleUnrated}
        >{$t('filter.unrated')}</button>
      {/if}

      <button
        type="button"
        class="flex items-center justify-center w-9 h-9 rounded-full shrink-0 bg-[#282828] text-[#b3b3b3] hover:bg-[#333] hover:text-white"
        title={$t('common.refresh')}
        aria-label={$t('filter.refreshList')}
        data-testid="chip-refresh"
        onclick={handleChange}
      >
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M23 4v6h-6"></path>
          <path d="M1 20v-6h6"></path>
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
        </svg>
      </button>
    </div>
  </div>

  {#if openSheet === 'genre'}
    <BottomSheet title={$t('nav.genres')} onclose={() => (openSheet = null)}>
      <div role="listbox" aria-label={$t('nav.genres')}>
        {@render sheetOption($t('filter.allGenres'), genre === '', () => selectGenre(''))}
        {#each genres as g (g.value)}
          {@render sheetOption(`${g.value} (${g.songCount})`, genre === g.value, () => selectGenre(g.value))}
        {/each}
      </div>
    </BottomSheet>
  {:else if openSheet === 'year'}
    <BottomSheet title={$t('filter.year')} onclose={() => (openSheet = null)}>
      <div role="listbox" aria-label={$t('filter.year')}>
        {@render sheetOption($t('filter.allYears'), year === '', () => selectYear(''))}
        {#each years as y (y.value)}
          {@render sheetOption(y.value, year === y.value, () => selectYear(y.value))}
        {/each}
      </div>
    </BottomSheet>
  {:else if openSheet === 'role'}
    <BottomSheet title={$t('filter.role')} onclose={() => (openSheet = null)}>
      <div role="listbox" aria-label={$t('filter.role')}>
        {#each roles as r (r.value)}
          {@render sheetOption($t(r.labelKey), role === r.value, () => selectRole(r.value))}
        {/each}
      </div>
    </BottomSheet>
  {:else if openSheet === 'rating'}
    <BottomSheet title={$t('filter.rating')} onclose={() => (openSheet = null)}>
      <div role="listbox" aria-label={$t('filter.rating')}>
        {@render sheetOption($t('filter.allRatings'), minRating === '0', () => selectRating('0'))}
        {#each [1, 2, 3, 4] as star (star)}
          {@render sheetOption($t('filter.starsMin', { count: star }), minRating === String(star), () => selectRating(String(star)))}
        {/each}
        {@render sheetOption($t('filter.starsExactly', { count: 5 }), minRating === '5', () => selectRating('5'))}
      </div>
    </BottomSheet>
  {:else if openSheet === 'quality'}
    <BottomSheet title={$t('filter.quality.label')} onclose={() => (openSheet = null)}>
      <div role="listbox" aria-label={$t('filter.quality.label')}>
        {@render sheetOption($t('filter.quality.any'), minQuality === '', () => selectQuality(''))}
        {#each QUALITY_FLOORS as tier (tier)}
          {@render sheetOption($t(QUALITY_LABEL_KEYS[tier]), minQuality === tier, () => selectQuality(tier))}
        {/each}
      </div>
    </BottomSheet>
  {:else if openSheet === 'sort'}
    <BottomSheet title={$t('filter.sortBy')} onclose={() => (openSheet = null)}>
      <div role="listbox" aria-label={$t('filter.sortBy')}>
        {#each allSortOptions[view] || [] as option (option.id)}
          {#if $visibleSortOptions[view]?.includes(option.id)}
            {@render sheetOption($t(option.labelKey), sort === option.id, () => selectSort(option.id))}
          {/if}
        {/each}
      </div>
    </BottomSheet>
  {/if}
{:else}
  <div class="flex flex-col gap-4 mb-6 bg-[#181818] p-3 md:p-4 rounded-lg">
    <div class="w-full">
      <input
        type="text"
        placeholder={$t('common.searchPlaceholder')}
        class="w-full bg-[#282828] text-white border-none px-4 py-2 rounded-[20px] text-sm focus:outline focus:outline-1 focus:outline-brand focus:bg-[#333]"
        bind:value={search}
        oninput={handleSearchInput}
      />
    </div>

    <div class="flex flex-wrap gap-x-6 gap-y-4 items-center">
      {#if (view === 'songs' || view === 'albums') && showGenre}
        <div class="flex items-center gap-2">
          <label for="genre" class="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-wider">{$t('nav.genres')}</label>
          <select id="genre" class="bg-[#282828] text-white border-none px-3 py-1.5 rounded text-sm cursor-pointer focus:outline focus:outline-1 focus:outline-brand" bind:value={genre} onchange={handleChange}>
            <option value="">{$t('filter.allGenres')}</option>
            {#each genres as g (g.value)}
              <option value={g.value}>{g.value} ({g.songCount})</option>
            {/each}
          </select>
        </div>
      {/if}

      {#if view === 'songs' && showYear}
        <div class="flex items-center gap-2">
          <label for="year" class="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-wider">{$t('filter.year')}</label>
          <select id="year" class="bg-[#282828] text-white border-none px-3 py-1.5 rounded text-sm cursor-pointer focus:outline focus:outline-1 focus:outline-brand" bind:value={year} onchange={handleChange}>
            <option value="">{$t('filter.allYears')}</option>
            {#each years as y (y.value)}
              <option value={y.value}>{y.value}</option>
            {/each}
          </select>
        </div>
      {/if}

      {#if view === 'artists'}
        <div class="flex items-center gap-2">
          <label for="role" class="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-wider">{$t('filter.role')}</label>
          <select id="role" class="bg-[#282828] text-white border-none px-3 py-1.5 rounded text-sm cursor-pointer focus:outline focus:outline-1 focus:outline-brand" bind:value={role} onchange={handleChange}>
            {#each roles as r (r.value)}
              <option value={r.value}>{$t(r.labelKey)}</option>
            {/each}
          </select>
        </div>
      {/if}

      {#if view === 'songs'}
        <div class="flex items-center gap-4">
          <div class="flex items-center gap-2">
            <label for="minRating" class="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-wider">{$t('filter.rating')}</label>
            <select id="minRating" class="bg-[#282828] text-white border-none px-3 py-1.5 rounded text-sm cursor-pointer focus:outline focus:outline-1 focus:outline-brand" bind:value={minRating} onchange={handleChange}>
              <option value="0">{$t('filter.allRatings')}</option>
              <option value="1">{$t('filter.starsMin', { count: 1 })}</option>
              <option value="2">{$t('filter.starsMin', { count: 2 })}</option>
              <option value="3">{$t('filter.starsMin', { count: 3 })}</option>
              <option value="4">{$t('filter.starsMin', { count: 4 })}</option>
              <option value="5">{$t('filter.starsExactly', { count: 5 })}</option>
            </select>
          </div>

          <div class="flex items-center gap-2">
            <label for="minQuality" class="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-wider">{$t('filter.quality.label')}</label>
            <select id="minQuality" class="bg-[#282828] text-white border-none px-3 py-1.5 rounded text-sm cursor-pointer focus:outline focus:outline-1 focus:outline-brand" bind:value={minQuality} onchange={handleChange}>
              <option value="">{$t('filter.quality.any')}</option>
              {#each QUALITY_FLOORS as tier (tier)}
                <option value={tier}>{$t(QUALITY_LABEL_KEYS[tier])}</option>
              {/each}
            </select>
          </div>

          <div class="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              id="unrated"
              class="w-4 h-4 accent-brand cursor-pointer"
              bind:checked={includeUnrated}
              onchange={handleChange}
            />
            <label for="unrated" class="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-wider cursor-pointer select-none">{$t('filter.unrated')}</label>
          </div>
        </div>
      {/if}

      <div class="flex items-center gap-2">
        <label for="sort" class="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-wider">{$t('filter.sortBy')}</label>
        <div class="flex items-center gap-1.5">
          <select id="sort" class="bg-[#282828] text-white border-none px-3 py-1.5 rounded text-sm cursor-pointer focus:outline focus:outline-1 focus:outline-brand" bind:value={sort} onchange={handleChange}>
            {#each allSortOptions[view] || [] as option (option.id)}
              {#if $visibleSortOptions[view]?.includes(option.id)}
                <option value={option.id}>{$t(option.labelKey)}</option>
              {/if}
            {/each}
          </select>
          <button
            type="button"
            class="bg-[#282828] text-[#b3b3b3] p-1.5 rounded hover:bg-[#333] hover:text-white transition-colors focus:outline focus:outline-1 focus:outline-brand"
            onclick={handleChange}
            title={$t('common.refresh')}
            aria-label={$t('filter.refreshList')}
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M23 4v6h-6"></path>
              <path d="M1 20v-6h6"></path>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
            </svg>
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
</style>
