<script>
  import { onMount, createEventDispatcher } from 'svelte';
  import { authParams } from './store.js';
  const dispatch = createEventDispatcher();

  export let genre = '';
  export let sort = 'recent';
  export let year = '';

  let genres = [];
  let years = [];

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
    dispatch('change', { genre, sort, year });
  }
</script>

<div class="filter-bar">
  <div class="filter-group">
    <label for="genre">Genre:</label>
    <select id="genre" bind:value={genre} on:change={handleChange}>
      <option value="">Alle Genres</option>
      {#each genres as g}
        <option value={g.value}>{g.value} ({g.songCount})</option>
      {/each}
    </select>
  </div>

  <div class="filter-group">
    <label for="year">Jaar:</label>
    <select id="year" bind:value={year} on:change={handleChange}>
      <option value="">Alle Jaren</option>
      {#each years as y}
        <option value={y.value}>{y.value}</option>
      {/each}
    </select>
  </div>

  <div class="filter-group">
    <label for="sort">Sorteer op:</label>
    <select id="sort" bind:value={sort} on:change={handleChange}>
      <option value="recent">Recent uitgebracht</option>
      <option value="releasedate">Release datum</option>
      <option value="added">Recent toegevoegd</option>
      <option value="alpha">Alfabetisch</option>
      <option value="random">Willekeurig</option>
    </select>
  </div>
</div>

<style>
  .filter-bar {
    display: flex;
    gap: 24px;
    margin-bottom: 24px;
    background-color: #181818;
    padding: 12px 16px;
    border-radius: 8px;
    align-items: center;
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
