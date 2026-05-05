<script>
  import { onMount } from 'svelte';
  import TrackCard from './TrackCard.svelte';
  import TrackList from './TrackList.svelte';
  import FilterBar from './FilterBar.svelte';
  import PlaylistView from './PlaylistView.svelte';
  import ArtistView from './ArtistView.svelte';
  import AlbumView from './AlbumView.svelte';
  import ArtistList from './ArtistList.svelte';
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
  let tracksOffset = 0;
  let tracksHasMore = true;
  let albumsOffset = 0;
  let albumsHasMore = true;
  let artistsOffset = 0;
  let artistsHasMore = true;
  const pageSize = 50;
  let currentGenre = '';
  let currentSort = 'recent';
  let currentYear = '';
  let currentTrackSearch = '';

  let currentArtistSort = 'alphabetical';
  let currentArtistRole = 'all';
  let currentArtistSearch = '';

  let currentAlbumSort = 'newest';
  let currentAlbumGenre = '';
  let currentAlbumSearch = '';

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

  async function loadAllTracks(append = false) {
    if (!$authParams) return;
    if (!append) {
      tracksOffset = 0;
      tracksHasMore = true;
    }
    if (!tracksHasMore) return;

    console.log(`Loading all tracks, activeView=${activeView}, genre=${currentGenre}, sort=${currentSort}, year=${currentYear}, offset=${tracksOffset}`);
    isLoading = true;
    try {
      let url = `/rest/getSpotifyTracks?sort=${currentSort}&offset=${tracksOffset}&count=${pageSize}&${$authParams}`;
      if (currentTrackSearch) url += `&query=${encodeURIComponent(currentTrackSearch)}`;
      if (currentGenre) url += `&genre=${encodeURIComponent(currentGenre)}`;
      else if (activeView.startsWith('genre:')) {
          const genreName = activeView.split(':')[1];
          url += `&genre=${encodeURIComponent(genreName)}`;
      }
      
      if (currentYear) url += `&year=${encodeURIComponent(currentYear)}`;

      if (activeView === 'sets') {
          url += `&minDuration=10`;
      } else {
          url += `&maxDuration=10`;
      }

      console.log(`Fetching: ${url}`);
      const response = await fetch(url);
      const data = await response.json();
      console.log("Track data received:", data);
      const result = data['subsonic-response']?.tracks?.track || [];
      const newTracks = Array.isArray(result) ? result : [result];
      
      if (append) {
        tracks = [...tracks, ...newTracks];
      } else {
        tracks = newTracks;
      }
      
      tracksOffset += newTracks.length;
      tracksHasMore = newTracks.length === pageSize;
    } catch (e) {
      console.error("Failed to load tracks:", e);
    } finally {
      isLoading = false;
    }
  }

  async function loadAlbums(append = false) {
    if (!$authParams) return;
    if (!append) {
      albumsOffset = 0;
      albumsHasMore = true;
    }
    if (!albumsHasMore) return;

    try {
      let url = `/rest/getAlbumList2?type=${currentAlbumSort}&size=${pageSize}&offset=${albumsOffset}&${$authParams}`;
      if (currentAlbumGenre) url += `&genre=${encodeURIComponent(currentAlbumGenre)}`;
      if (currentAlbumSearch) url += `&query=${encodeURIComponent(currentAlbumSearch)}`;

      const response = await fetch(url);
      const data = await response.json();
      const result = data['subsonic-response']?.albumList2?.album || [];
      const newAlbums = Array.isArray(result) ? result : [result];
      
      if (append) {
        albums = [...albums, ...newAlbums];
      } else {
        albums = newAlbums;
      }
      
      albumsOffset += newAlbums.length;
      albumsHasMore = newAlbums.length === pageSize;
    } catch (e) { console.error(e); }
  }

  async function loadArtists(append = false) {
    if (!$authParams) return;
    if (!append) {
      artistsOffset = 0;
      artistsHasMore = true;
    }
    if (!artistsHasMore) return;

    try {
      let url = `/rest/getArtistList?type=${currentArtistSort}&role=${currentArtistRole}&size=${pageSize}&offset=${artistsOffset}&${$authParams}`;
      if (currentArtistSearch) url += `&query=${encodeURIComponent(currentArtistSearch)}`;
      
      const response = await fetch(url);
      const data = await response.json();
      const result = data['subsonic-response']?.artistList?.artist || [];
      const newArtists = Array.isArray(result) ? result : [result];
      
      if (append) {
        artists = [...artists, ...newArtists];
      } else {
        artists = newArtists;
      }
      
      artistsOffset += newArtists.length;
      artistsHasMore = newArtists.length === pageSize;
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

  function handleNavigate(view) {
    activeView = view;
  }

  function handleFilterChange(e) {
      const { genre, sort, year, search, role } = e.detail;
      if (activeView === 'artists') {
          currentArtistSort = sort;
          currentArtistRole = role;
          currentArtistSearch = search;
          loadArtists();
      } else if (activeView === 'albums') {
          currentAlbumSort = sort;
          currentAlbumGenre = genre;
          currentAlbumSearch = search;
          loadAlbums();
      } else {
          currentGenre = genre;
          currentSort = sort;
          currentYear = year;
          currentTrackSearch = search;
          loadAllTracks();
      }
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
            <TrackCard {track} on:navigate={(e) => activeView = e.detail} />
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
        <FilterBar view="songs" genre={currentGenre} sort={currentSort} year={currentYear} search={currentTrackSearch} on:change={handleFilterChange} />
    </div>
    {#if isLoading && tracks.length === 0}
        <p>Laden...</p>
    {:else}
        <TrackList {tracks} on:navigate={(e) => activeView = e.detail} />
        {#if tracksHasMore}
            <div class="load-more">
                <button on:click={() => loadAllTracks(true)}>Meer laden</button>
            </div>
        {/if}
    {/if}
  {:else if activeView === 'albums'}
    <div class="view-header">
      <h2>Albums</h2>
      <FilterBar view="albums" genre={currentAlbumGenre} sort={currentAlbumSort} search={currentAlbumSearch} on:change={handleFilterChange} />
    </div>
    <div class="grid">
        {#each albums as album}
            <div class="card" on:click={() => activeView = `album:${album.id}`}>
                <img 
                  src={album.coverArt ? `/rest/getCoverArt?id=${album.coverArt}&size=300&${$authParams}` : '/images/spotify-fallback.svg'} 
                  alt={album.name} 
                  on:error={(e) => e.target.src = '/images/spotify-fallback.svg'}
                />
                <span class="title">{album.name}</span>
                <ArtistList 
                  artist={album.artist} 
                  artistId={album.artistId} 
                  artists={album.albumArtists} 
                  on:navigate={(e) => activeView = e.detail} 
                />
            </div>
        {/each}
    </div>
    {#if albumsHasMore}
        <div class="load-more">
            <button on:click={() => loadAlbums(true)}>Meer laden</button>
        </div>
    {/if}
  {:else if activeView === 'artists'}
    <div class="view-header">
      <h2>Artiesten</h2>
      <FilterBar view="artists" sort={currentArtistSort} role={currentArtistRole} search={currentArtistSearch} on:change={handleFilterChange} />
    </div>
    <div class="grid">
        {#each artists as artist}
            <div class="card artist-card" on:click={() => activeView = `artist:${artist.id}`}>
                <img src={artist.coverArt ? `/rest/getCoverArt?id=${artist.coverArt}&size=300&${$authParams}` : '/images/unknown-artist.svg'} alt={artist.name} />
                <span class="title">{artist.name}</span>
                <span class="artist">Artiest</span>
            </div>
        {/each}
    </div>
    {#if artistsHasMore}
        <div class="load-more">
            <button on:click={() => loadArtists(true)}>Meer laden</button>
        </div>
    {/if}
  {:else if activeView === 'playlists'}
    <h2>Afspeellijsten</h2>
    <div class="grid">
        {#each playlists as playlist}
            <div class="card" on:click={() => openPlaylist(playlist)}>
                <img 
                  src={playlist.coverArt ? `/rest/getCoverArt?id=${playlist.coverArt}&size=300&${$authParams}` : '/images/spotify-fallback.svg'} 
                  alt={playlist.name} 
                  on:error={(e) => e.target.src = '/images/spotify-fallback.svg'}
                />
                <span class="title">{playlist.name}</span>
            </div>
        {/each}
    </div>
  {:else if activeView === 'playlist-detail'}
    <PlaylistView />
  {:else if activeView.startsWith('artist:')}
    <ArtistView artistId={activeView.split(':')[1]} onNavigate={handleNavigate} />
  {:else if activeView.startsWith('album:')}
    <AlbumView albumId={activeView.split(':')[1]} onNavigate={handleNavigate} />
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
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .load-more {
    display: flex;
    justify-content: center;
    padding: 24px 0;
  }

  .load-more button {
    background-color: transparent;
    border: 1px solid #727272;
    color: white;
    padding: 8px 32px;
    border-radius: 24px;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.2s;
  }

  .load-more button:hover {
    border-color: white;
    transform: scale(1.04);
  }

  .empty-msg {
    color: #b3b3b3;
    grid-column: 1 / -1;
  }
</style>
