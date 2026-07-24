<script>

  import { authParams, visibleSortOptions, allSortOptions } from './store.js';

  let {
    genre = $bindable(''),
    sort = $bindable('recent'),
    year = $bindable(''),
    search = $bindable(''),
    minRating = $bindable('0'),
    includeUnrated = $bindable(true),
    role = $bindable('all'),
    view = 'songs',
    showGenre = true,
    onchange
  } = $props();

  let genres = $state([]);
  let years = $state([]);

  const roles = [
    { value: 'all', label: 'Alle rollen' },
    { value: 'release', label: 'Album artiesten' },
    { value: 'track', label: 'Nummer artiesten' },
    { value: 'composer', label: 'Componisten' },
    { value: 'conductor', label: 'Dirigenten' },
    { value: 'lyricist', label: 'Tekstschrijvers' },
    { value: 'mixer', label: 'Mixers' },
    { value: 'performer', label: 'Performers' },
    { value: 'producer', label: 'Producers' },
    { value: 'remixer', label: 'Remixers' },
    { value: 'writer', label: 'Schrijvers' }
  ];

  /**
   * Fetches the list of all available genres from the server.
   */
  async function loadGenres() {
    if (!$authParams) return;
    try {
        const response = await fetch(`/rest/getGenres?${$authParams}`);
        if (response.ok) {
            const data = await response.json();
            const result = data['subsonic-response']?.genres?.genre || [];
            const resultArr = Array.isArray(result) ? result : [result];
            genres = resultArr
                .filter(g => Number(g.songCount) >= 10)
                .sort((a, b) => a.value.localeCompare(b.value));
        }
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
        const response = await fetch(`/rest/getYears?${$authParams}`);
        if (response.ok) {
            const data = await response.json();
            const result = data['subsonic-response']?.years?.year || [];
            const sortedYears = Array.isArray(result) ? result : [result];
            sortedYears.sort((a, b) => b.value.localeCompare(a.value));
            years = sortedYears;
        }
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
    if (onchange) onchange({ genre, sort, year, search, role, minRating, includeUnrated });
  }

  let searchTimeout;
  /**
   * Handles search input with a debounced notification to the parent.
   */
  function handleSearchInput() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(handleChange, 500);
  }
</script>

<div class="flex flex-col gap-4 mb-6 bg-[#181818] p-3 md:p-4 rounded-lg">
  <div class="w-full">
    <input
      type="text"
      placeholder="Zoeken..."
      class="w-full bg-[#282828] text-white border-none px-4 py-2 rounded-[20px] text-sm focus:outline focus:outline-1 focus:outline-brand focus:bg-[#333]"
      bind:value={search}
      oninput={handleSearchInput}
    />
  </div>

  <div class="flex flex-wrap gap-x-6 gap-y-4 items-center">
    {#if (view === 'songs' || view === 'albums') && showGenre}
      <div class="flex items-center gap-2">
        <label for="genre" class="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-wider">Genre</label>
        <select id="genre" class="bg-[#282828] text-white border-none px-3 py-1.5 rounded text-sm cursor-pointer focus:outline focus:outline-1 focus:outline-brand" bind:value={genre} onchange={handleChange}>
          <option value="">Alle Genres</option>
          {#each genres as g (g.value)}
            <option value={g.value}>{g.value} ({g.songCount})</option>
          {/each}
        </select>
      </div>
    {/if}

    {#if view === 'songs'}
      <div class="flex items-center gap-2">
        <label for="year" class="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-wider">Jaar</label>
        <select id="year" class="bg-[#282828] text-white border-none px-3 py-1.5 rounded text-sm cursor-pointer focus:outline focus:outline-1 focus:outline-brand" bind:value={year} onchange={handleChange}>
          <option value="">Alle Jaren</option>
          {#each years as y (y.value)}
            <option value={y.value}>{y.value}</option>
          {/each}
        </select>
      </div>
    {/if}

    {#if view === 'artists'}
      <div class="flex items-center gap-2">
        <label for="role" class="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-wider">Rol</label>
        <select id="role" class="bg-[#282828] text-white border-none px-3 py-1.5 rounded text-sm cursor-pointer focus:outline focus:outline-1 focus:outline-brand" bind:value={role} onchange={handleChange}>
          {#each roles as r (r.value)}
            <option value={r.value}>{r.label}</option>
          {/each}
        </select>
      </div>
    {/if}

    {#if view === 'songs'}
      <div class="flex items-center gap-4">
        <div class="flex items-center gap-2">
          <label for="minRating" class="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-wider">Rating</label>
          <select id="minRating" class="bg-[#282828] text-white border-none px-3 py-1.5 rounded text-sm cursor-pointer focus:outline focus:outline-1 focus:outline-brand" bind:value={minRating} onchange={handleChange}>
            <option value="0">Alle</option>
            <option value="1">1+ sterren</option>
            <option value="2">2+ sterren</option>
            <option value="3">3+ sterren</option>
            <option value="4">4+ sterren</option>
            <option value="5">5 sterren</option>
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
          <label for="unrated" class="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-wider cursor-pointer select-none">Unrated</label>
        </div>
      </div>
    {/if}

    <div class="flex items-center gap-2">
      <label for="sort" class="text-[11px] font-bold text-[#b3b3b3] uppercase tracking-wider">Sorteer op</label>
      <div class="flex items-center gap-1.5">
        <select id="sort" class="bg-[#282828] text-white border-none px-3 py-1.5 rounded text-sm cursor-pointer focus:outline focus:outline-1 focus:outline-brand" bind:value={sort} onchange={handleChange}>
          {#each allSortOptions[view] || [] as option}
            {#if $visibleSortOptions[view]?.includes(option.id)}
              <option value={option.id}>{option.label}</option>
            {/if}
          {/each}
        </select>
        <button
          type="button"
          class="bg-[#282828] text-[#b3b3b3] p-1.5 rounded hover:bg-[#333] hover:text-white transition-colors focus:outline focus:outline-1 focus:outline-brand"
          onclick={handleChange}
          title="Vernieuwen"
          aria-label="Lijst vernieuwen"
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

<style>
</style>
