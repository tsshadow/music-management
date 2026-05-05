<script>
  import { onMount, createEventDispatcher } from 'svelte';
  import { authParams } from './store.js';
  const dispatch = createEventDispatcher();

  export let view = 'songs';
  export let genre = '';
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
    loadGenres();
    loadYears();
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

<div class="filter-bar">
  <div class="search-group">
    <input 
      type="text" 
      placeholder="Zoeken..." 
      bind:value={search} 
      on:input={handleSearchInput}
    />
  </div>

  {#if view === 'songs' || view === 'albums'}
    <div class="filter-group">
      <label for="genre">Genre:</label>
      <select id="genre" bind:value={genre} on:change={handleChange}>
        <option value="">Alle Genres</option>
        {#each genres as g}
          <option value={g.value}>{g.value} ({g.songCount})</option>
        {/each}
      </select>
    </div>
  {/if}

  {#if view === 'songs'}
    <div class="filter-group">
      <label for="year">Jaar:</label>
      <select id="year" bind:value={year} on:change={handleChange}>
        <option value="">Alle Jaren</option>
        {#each years as y}
          <option value={y.value}>{y.value}</option>
        {/each}
      </select>
    </div>
  {/if}

  {#if view === 'artists'}
    <div class="filter-group">
      <label for="role">Rol:</label>
      <select id="role" bind:value={role} on:change={handleChange}>
        {#each roles as r}
          <option value={r.value}>{r.label}</option>
        {/each}
      </select>
    </div>
  {/if}

  <div class="filter-group">
    <label for="sort">Sorteer op:</label>
    <select id="sort" bind:value={sort} on:change={handleChange}>
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
  .filter-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    margin-bottom: 24px;
    background-color: #181818;
    padding: 12px 16px;
    border-radius: 8px;
    align-items: center;
  }

  .search-group {
    flex: 1;
    min-width: 200px;
  }

  .search-group input {
    width: 100%;
    background-color: #282828;
    color: #fff;
    border: none;
    padding: 8px 16px;
    border-radius: 20px;
    font-size: 14px;
  }

  .search-group input:focus {
    outline: 1px solid #1db954;
    background-color: #333;
  }

  .filter-group {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  label {
    font-size: 12px;
    font-weight: 700;
    color: #b3b3b3;
    text-transform: uppercase;
  }

  select {
    background-color: #282828;
    color: #fff;
    border: none;
    padding: 6px 12px;
    border-radius: 4px;
    font-size: 14px;
    cursor: pointer;
  }

  select:focus {
    outline: 1px solid #1db954;
  }
</style>
