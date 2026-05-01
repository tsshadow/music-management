<script>
  import { onMount } from 'svelte';
  import TrackCard from './TrackCard.svelte';

  export let activeView = 'home';

  let sections = [
    { title: 'Release Radar', endpoint: 'releaseRadar', tracks: [] },
    { title: 'Recent Raw Hardstyle', endpoint: 'genre/raw%20hardstyle', tracks: [] },
    { title: 'Recent Hardcore', endpoint: 'genre/hardcore', tracks: [] },
    { title: 'Sets (>10m)', endpoint: 'sets', tracks: [] }
  ];

  async function fetchTracks(endpoint) {
    try {
        // We gebruiken de nieuwe Spotify endpoints die ik in de backend heb toegevoegd
        const response = await fetch(`/rest/spotify/${endpoint}`);
        if (!response.ok) throw new Error('Network response was not ok');
        const data = await response.json();
        return data.tracks || [];
    } catch (e) {
        console.error(`Failed to fetch ${endpoint}:`, e);
        return [];
    }
  }

  onMount(async () => {
    // In een echte app zouden we dit doen, maar voor nu vullen we wat mock data
    // als de API nog niet helemaal live is of als we in dev mode zijn.
    for (let section of sections) {
        section.tracks = await fetchTracks(section.endpoint);
    }
    sections = [...sections];
  });
</script>

<div class="dashboard">
  {#if activeView === 'home'}
    {#each sections as section}
      <section class="row">
        <div class="row-header">
          <h2>{section.title}</h2>
          <button class="show-all">Alles tonen</button>
        </div>
        <div class="grid">
          {#each section.tracks.slice(0, 6) as track}
            <TrackCard {track} />
          {/each}
          {#if section.tracks.length === 0}
            <p class="empty-msg">Geen tracks gevonden in deze categorie.</p>
          {/if}
        </div>
      </section>
    {/each}
  {:else if activeView === 'songs'}
    <h2>Alle Nummers</h2>
    <!-- Implementatie voor alle nummers -->
  {:else if activeView === 'sets'}
    <h2>Sets (> 10 minuten)</h2>
    <!-- Implementatie voor sets -->
  {/if}
</div>

<style>
  .dashboard {
    display: flex;
    flex-direction: column;
    gap: 32px;
  }

  .row-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    margin-bottom: 16px;
  }

  h2 {
    font-size: 24px;
    font-weight: 700;
    margin: 0;
  }

  .show-all {
    background: none;
    border: none;
    color: #b3b3b3;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  .show-all:hover {
    text-decoration: underline;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 24px;
  }

  .empty-msg {
    color: #b3b3b3;
    grid-column: 1 / -1;
  }
</style>
