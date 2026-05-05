<script>
  import { onMount } from 'svelte';
  import TrackCard from './TrackCard.svelte';
  import TrackList from './TrackList.svelte';
  import FilterBar from './FilterBar.svelte';
  import PlaylistView from './PlaylistView.svelte';
  import { authParams, currentPlaylist } from './store.js';

  export let activeView = 'home';

  let sections = [
    { title: 'Release Radar', id: 'spotify:release_radar', tracks: [] },
    { title: 'Recent Raw Hardstyle', id: 'spotify:genre:raw hardstyle', tracks: [] },
    { title: 'Recent Hardcore', id: 'spotify:genre:hardcore', tracks: [] },
    { title: 'Sets', id: 'spotify:sets', tracks: [] }
  ];

  let tracks = [];
  let albums = [];
  let artists = [];
  let playlists = [];
  let currentGenre = '';
  let currentSort = 'recent';
  let currentYear = '';
  let isLoading = false;

  async function fetchTracks(id) {
    if (!$authParams) return [];
    console.log(`Fetching tracks for curated playlist: ${id}`);
    try {
        const response = await fetch(`/rest/getSpotifyPlaylist?id=${encodeURIComponent(id)}&${$authParams}`);
        if (!response.ok) throw new Error('Network response was not ok');
        const data = await response.json();
        console.log(`Data for ${id}:`, data);
        const result = data['subsonic-response']?.playlist?.entry || [];
        return Array.isArray(result) ? result : [result];
    } catch (e) {
        console.error(`Failed to fetch ${id}:`, e);
        return [];
    }
  }

  async function loadAllTracks() {
    if (!$authParams) return;
    console.log(`Loading all tracks, activeView=${activeView}, genre=${currentGenre}, sort=${currentSort}, year=${currentYear}`);
    isLoading = true;
    try {
      let url = `/rest/getSpotifyTracks?sort=${currentSort}&${$authParams}`;
      if (currentGenre) url += `&genre=${encodeURIComponent(currentGenre)}`;
      else if (activeView.startsWith('genre:')) {
          const genreName = activeView.split(':')[1];
          url += `&genre=${encodeURIComponent(genreName)}`;
      }
      
      if (currentYear) url += `&year=${encodeURIComponent(currentYear)}`;

      if (activeView === 'sets') url += `&minDuration=10`;

      console.log(`Fetching: ${url}`);
      const response = await fetch(url);
      const data = await response.json();
      console.log("Track data received:", data);
      const result = data['subsonic-response']?.tracks?.track || [];
      tracks = Array.isArray(result) ? result : [result];
    } catch (e) {
      console.error("Failed to load tracks:", e);
    } finally {
      isLoading = false;
    }
  }

  async function loadAlbums() {
    if (!$authParams) return;
    try {
      const response = await fetch(`/rest/getAlbumList2?type=newest&size=50&${$authParams}`);
      const data = await response.json();
      albums = data['subsonic-response']?.albumList2?.album || [];
    } catch (e) { console.error(e); }
  }

  async function loadArtists() {
    if (!$authParams) return;
    try {
      const response = await fetch(`/rest/getArtists?${$authParams}`);
      const data = await response.json();
      // Subsonic artists zijn gegroepeerd per index (A, B, C...)
      const indexes = data['subsonic-response']?.artists?.index || [];
      artists = indexes.flatMap(idx => idx.artist || []);
    } catch (e) { console.error(e); }
  }

  async function loadPlaylists() {
    if (!$authParams) return;
    try {
      const response = await fetch(`/rest/getPlaylists?${$authParams}`);
      const data = await response.json();
      playlists = data['subsonic-response']?.playlists?.playlist || [];
    } catch (e) { console.error(e); }
  }

  function openRadar() {
      openPlaylist({ id: 'spotify:release_radar', name: 'Release Radar', coverArt: 'spotify:release_radar' });
  }

  function openPlaylist(playlist) {
    currentPlaylist.set(playlist);
    activeView = 'playlist-detail';
  }

  function handleFilterChange(e) {
      const { genre, sort, year } = e.detail;
      currentGenre = genre;
      currentSort = sort;
      currentYear = year;
      loadAllTracks();
  }

  async function loadCurated() {
    for (let section of sections) {
        section.tracks = await fetchTracks(section.id);
    }
    sections = [...sections];
  }

  $: if ($authParams) {
    if (activeView === 'home') {
        loadCurated();
    } else if (activeView === 'songs' || activeView === 'sets' || activeView.startsWith('genre:')) {
        loadAllTracks();
    } else if (activeView === 'radar') {
        openRadar();
    } else if (activeView === 'albums') {
        loadAlbums();
    } else if (activeView === 'artists') {
        loadArtists();
    } else if (activeView === 'playlists') {
        loadPlaylists();
    }
  }
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
  {:else if activeView === 'songs' || activeView === 'sets' || activeView.startsWith('genre:')}
    <div class="view-header">
        <h2>
            {#if activeView === 'songs'}Alle Nummers{:else if activeView === 'sets'}Sets{:else}{activeView.split(':')[1]}{/if}
        </h2>
        <FilterBar genre={currentGenre} sort={currentSort} year={currentYear} on:change={handleFilterChange} />
    </div>
    {#if isLoading}
        <p>Laden...</p>
    {:else}
        <TrackList {tracks} />
    {/if}
  {:else if activeView === 'albums'}
    <h2>Albums</h2>
    <div class="grid">
        {#each albums as album}
            <div class="card">
                <img src={album.coverArt ? `/rest/getCoverArt?id=${album.coverArt}&size=300&${$authParams}` : '/images/unknown-cover.svg'} alt={album.name} />
                <span class="title">{album.name}</span>
                <span class="artist">{album.artist}</span>
            </div>
        {/each}
    </div>
  {:else if activeView === 'artists'}
    <h2>Artiesten</h2>
    <div class="grid">
        {#each artists as artist}
            <div class="card artist-card">
                <img src={artist.coverArt ? `/rest/getCoverArt?id=${artist.coverArt}&size=300&${$authParams}` : '/images/unknown-artist.svg'} alt={artist.name} />
                <span class="title">{artist.name}</span>
                <span class="artist">Artiest</span>
            </div>
        {/each}
    </div>
  {:else if activeView === 'playlists'}
    <h2>Afspeellijsten</h2>
    <div class="grid">
        {#each playlists as playlist}
            <div class="card" on:click={() => openPlaylist(playlist)}>
                <img src={playlist.coverArt ? `/rest/getCoverArt?id=${playlist.coverArt}&size=300&${$authParams}` : '/images/unknown-cover.svg'} alt={playlist.name} />
                <span class="title">{playlist.name}</span>
                <span class="artist">{playlist.owner}</span>
            </div>
        {/each}
    </div>
  {:else if activeView === 'playlist-detail'}
    <PlaylistView />
  {/if}
</div>

<style>
  .dashboard {
    display: flex;
    flex-direction: column;
    gap: 32px;
  }

  .view-header {
      display: flex;
      flex-direction: column;
      gap: 16px;
      margin-bottom: 24px;
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

  .card {
    background-color: #181818;
    padding: 16px;
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    cursor: pointer;
    transition: background-color 0.3s;
  }

  .card:hover {
    background-color: #282828;
  }

  .card img {
    width: 100%;
    aspect-ratio: 1;
    object-fit: cover;
    border-radius: 4px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.5);
  }

  .artist-card img {
    border-radius: 50%;
  }

  .card .title {
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .card .artist {
    font-size: 14px;
    color: #b3b3b3;
  }

  .empty-msg {
    color: #b3b3b3;
    grid-column: 1 / -1;
  }
</style>
