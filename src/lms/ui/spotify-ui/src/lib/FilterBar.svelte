<script>
  import { onMount, createEventDispatcher } from 'svelte';
  import { authParams } from './store.js';
  const dispatch = createEventDispatcher();

  export let genre = '';
  export let sort = 'recent';

  let genres = [];

  async function loadGenres() {
    if (!$authParams) return;
    try {
        const response = await fetch(`/rest/getGenres?${$authParams}`);
        if (response.ok) {
            const data = await response.json();
            genres = data['subsonic-response']?.genres?.genre || [];
        }
    } catch (e) {
        console.error("Failed to fetch genres:", e);
    }
  }

  $: if ($authParams) {
    loadGenres();
  }

  function handleChange() {
    dispatch('change', { genre, sort });
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
    <label for="sort">Sorteer op:</label>
    <select id="sort" bind:value={sort} on:change={handleChange}>
      <option value="recent">Recent uitgebracht</option>
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
