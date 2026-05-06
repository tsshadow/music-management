<script>
  import { createEventDispatcher } from 'svelte';
  import { authParams } from './store.js';
  const dispatch = createEventDispatcher();

  export let view = 'songs';
  export let genre = '';
  export let showGenre = true;
  export let sort = 'recent';
  export let year = '';
  export let search = '';
  export let role = 'all';

  let genres = [];
  let years = [];

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

  async function loadGenres() {
    if (!$authParams) return;
    console.log("Loading genres...");
    try {
        const response = await fetch(`/rest/getGenres?${$authParams}`);
        if (response.ok) {
            const data = await response.json();
            console.log("Genres received:", data);
            const result = data['subsonic-response']?.genres?.genre || [];
            genres = Array.isArray(result) ? result : [result];
        } else {
            console.error("Failed to load genres, response not ok");
        }
    } catch (e) {
        console.error("Failed to fetch genres:", e);
    }
  }

  async function loadYears() {
    if (!$authParams) return;
    console.log("Loading years...");
    try {
        const response = await fetch(`/rest/getYears?${$authParams}`);
        if (response.ok) {
            const data = await response.json();
            console.log("Years received:", data);
            const result = data['subsonic-response']?.years?.year || [];
            years = Array.isArray(result) ? result : [result];
            // Sorteer jaren aflopend
            years.sort((a, b) => b.value.localeCompare(a.value));
        } else {
            console.error("Failed to load years, response not ok");
        }
    } catch (e) {
        console.error("Failed to fetch years:", e);
    }
  }

  $: if ($authParams) {
    void Promise.all([loadGenres(), loadYears()]);
  }

  function handleChange() {
    dispatch('change', { genre, sort, year, search, role });
  }

  let searchTimeout;
  function handleSearchInput() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(handleChange, 500);
  }
</script>

<div class="flex flex-wrap gap-4 mb-6 bg-[#181818] p-3 md:p-4 rounded-lg items-center">
  <div class="flex-1 min-w-[200px]">
    <input 
      type="text" 
      placeholder="Zoeken..." 
      class="w-full bg-[#282828] text-white border-none px-4 py-2 rounded-[20px] text-sm focus:outline focus:outline-1 focus:outline-spotify-green focus:bg-[#333]"
      bind:value={search} 
      on:input={handleSearchInput}
    />
  </div>

  {#if (view === 'songs' || view === 'albums') && showGenre}
    <div class="flex items-center gap-2">
      <label for="genre" class="text-[12px] font-bold text-[#b3b3b3] uppercase">Genre:</label>
      <select id="genre" class="bg-[#282828] text-white border-none px-3 py-1.5 rounded text-sm cursor-pointer focus:outline focus:outline-1 focus:outline-spotify-green" bind:value={genre} on:change={handleChange}>
        <option value="">Alle Genres</option>
        {#each genres as g (g.value)}
          <option value={g.value}>{g.value} ({g.songCount})</option>
        {/each}
      </select>
    </div>
  {/if}

  {#if view === 'songs'}
    <div class="flex items-center gap-2">
      <label for="year" class="text-[12px] font-bold text-[#b3b3b3] uppercase">Jaar:</label>
      <select id="year" class="bg-[#282828] text-white border-none px-3 py-1.5 rounded text-sm cursor-pointer focus:outline focus:outline-1 focus:outline-spotify-green" bind:value={year} on:change={handleChange}>
        <option value="">Alle Jaren</option>
        {#each years as y (y.value)}
          <option value={y.value}>{y.value}</option>
        {/each}
      </select>
    </div>
  {/if}

  {#if view === 'artists'}
    <div class="flex items-center gap-2">
      <label for="role" class="text-[12px] font-bold text-[#b3b3b3] uppercase">Rol:</label>
      <select id="role" class="bg-[#282828] text-white border-none px-3 py-1.5 rounded text-sm cursor-pointer focus:outline focus:outline-1 focus:outline-spotify-green" bind:value={role} on:change={handleChange}>
        {#each roles as r (r.value)}
          <option value={r.value}>{r.label}</option>
        {/each}
      </select>
    </div>
  {/if}

  <div class="flex items-center gap-2">
    <label for="sort" class="text-[12px] font-bold text-[#b3b3b3] uppercase">Sorteer op:</label>
    <select id="sort" class="bg-[#282828] text-white border-none px-3 py-1.5 rounded text-sm cursor-pointer focus:outline focus:outline-1 focus:outline-spotify-green" bind:value={sort} on:change={handleChange}>
      {#if view === 'songs'}
        <option value="recent">Recent uitgebracht</option>
        <option value="releasedate">Release datum</option>
        <option value="added">Recent toegevoegd</option>
        <option value="alpha">Alfabetisch</option>
        <option value="random">Willekeurig</option>
      {:else if view === 'albums'}
        <option value="newest">Recent toegevoegd</option>
        <option value="recent">Recent afgespeeld</option>
        <option value="alphabeticalByName">Alfabetisch (Titel)</option>
        <option value="alphabeticalByArtist">Alfabetisch (Artiest)</option>
        <option value="random">Willekeurig</option>
        <option value="starred">Favorieten</option>
      {:else if view === 'artists'}
        <option value="alphabetical">Alfabetisch</option>
        <option value="trackCount">Aantal nummers</option>
        <option value="newest">Recent toegevoegd</option>
        <option value="recent">Recent bijgewerkt</option>
        <option value="starred">Favorieten</option>
        <option value="random">Willekeurig</option>
      {/if}
    </select>
  </div>
</div>

<style>
</style>
