<script>
  import { untrack } from 'svelte';
  import TrackCard from './TrackCard.svelte';
  import TrackList from './TrackList.svelte';
  import FilterBar from './FilterBar.svelte';
  import PlaylistView from './PlaylistView.svelte';
  import ArtistView from './ArtistView.svelte';
  import AlbumView from './AlbumView.svelte';
  import ArtistList from './ArtistList.svelte';
  import Settings from './Settings.svelte';
  import { getArtistImageUrl } from './utils.js';
  import { authParams, currentPlaylist, viewMode } from './store.js';

  let { activeView = $bindable('home') } = $props();

  let sections = $state([
    { title: 'Release Radar', id: 'spotify:release_radar', tracks: [] },
    { title: 'Songs', id: 'spotify:songs', tracks: [] },
    { title: 'Sets', id: 'spotify:sets', tracks: [] }
  ]);

  let tracks = $state([]);
  let albums = $state([]);
  let artists = $state([]);
  let allGenres = $state([]);
  let playlists = $state([]);
  let tracksOffset = $state(0);
  let tracksHasMore = $state(true);
  let albumsOffset = $state(0);
  let albumsHasMore = $state(true);
  let artistsOffset = $state(0);
  let artistsHasMore = $state(true);
  const pageSize = 50;
  let currentGenre = $state('');
  let currentSort = $state('recent');
  let currentYear = $state('');
  let currentTrackSearch = $state('');
  let currentMinRating = $state('2');
  let includeUnrated = $state(true);

  let currentArtistSort = $state('alphabetical');
  let currentArtistRole = $state('all');
  let currentArtistSearch = $state('');

  let currentAlbumSort = $state('newest');
  let currentAlbumGenre = $state('');
  let currentAlbumSearch = $state('');

  let isLoading = $state(false);

  /**
   * Fetches tracks for a specific curated playlist.
   * 
   * @param {string} id - The Subsonic ID of the curated playlist.
   * @returns {Promise<Object[]>} A promise that resolves to an array of tracks.
   */
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

  /**
   * Loads tracks for the 'songs', 'sets', or 'genre' views with pagination.
   * 
   * @param {boolean} [append=false] - Whether to append new results to the existing tracks.
   */
  async function loadAllTracks(append = false) {
    if (!$authParams) return;
    if (!append) {
      tracksOffset = 0;
      tracksHasMore = true;
    }
    if (!tracksHasMore) return;

    console.log(`Loading all tracks, activeView=${activeView}, genre=${currentGenre}, sort=${currentSort}, year=${currentYear}, minRating=${currentMinRating}, offset=${tracksOffset}`);
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
      if (currentMinRating !== '0') url += `&minRating=${currentMinRating}`;
      if (includeUnrated) url += `&includeUnrated=true`;

      if ($viewMode === 'sets') {
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

  /**
   * Loads a list of albums with sorting, filtering, and pagination.
   * 
   * @param {boolean} [append=false] - Whether to append new results to the existing albums.
   */
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

  /**
   * Loads a list of artists with sorting, filtering, and pagination.
   * 
   * @param {boolean} [append=false] - Whether to append new results to the existing artists.
   */
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

  /**
   * Loads all user playlists from the server.
   */
  async function loadPlaylists() {
    if (!$authParams) return;
    try {
      const response = await fetch(`/rest/getPlaylists?${$authParams}`);
      const data = await response.json();
      playlists = data['subsonic-response']?.playlists?.playlist || [];
    } catch (e) { console.error(e); }
  }

  /**
   * Loads all genres from the server.
   */
  async function loadAllGenres() {
    if (!$authParams) return;
    isLoading = true;
    console.log("Fetching all genres...");
    try {
      const response = await fetch(`/rest/getGenres?${$authParams}`);
      const data = await response.json();
      console.log("Genres response:", data);
      const result = data['subsonic-response']?.genres?.genre || [];
      allGenres = Array.isArray(result) ? result : [result];
      console.log(`Loaded ${allGenres.length} genres`);
    } catch (e) { 
      console.error("Failed to load genres:", e); 
    } finally {
      isLoading = false;
    }
  }

  /**
   * Opens the "Release Radar" curated playlist.
   */
  function openRadar() {
      openPlaylist({ id: 'spotify:release_radar', name: 'Release Radar', coverArt: 'spotify:release_radar' });
  }

  /**
   * Switches the view to the details of a specific playlist.
   * 
   * @param {Object} playlist - The playlist object.
   */
  function openPlaylist(playlist) {
    currentPlaylist.set(playlist);
    activeView = 'playlist-detail';
  }

  /**
   * Handles changes from the FilterBar and reloads the appropriate data.
   * 
   * @param {Object} params - The filter and sort parameters.
   */
  function handleFilterChange(params) {
      const { genre, sort, year, search, role, minRating, includeUnrated: incUnrated } = params;
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
          currentMinRating = minRating || '0';
          includeUnrated = incUnrated !== undefined ? incUnrated : true;
          loadAllTracks();
      }
  }

  /**
   * Loads all curated sections (Release Radar, Songs, Sets) for the home view.
   */
  async function loadCurated() {
    const results = await Promise.all(sections.map(section => fetchTracks(section.id)));
    sections = sections.map((section, index) => {
      section.tracks = results[index];
      return section;
    });
  }

  $effect(() => {
    const view = activeView;
    const auth = $authParams;
    const mode = $viewMode;

    if (auth) {
      untrack(() => {
        if (view === 'home') {
            loadCurated();
        } else if (view === 'songs' || view === 'sets' || view.startsWith('genre:')) {
            loadAllTracks();
        } else if (view === 'radar') {
            openRadar();
        } else if (view === 'albums') {
            loadAlbums();
        } else if (view === 'genres') {
            loadAllGenres();
        } else if (view === 'artists') {
            loadArtists();
        } else if (view === 'playlists') {
            loadPlaylists();
        }
      });
    }
  });
</script>

<div class="flex flex-col gap-8">
  {#if activeView === 'home'}
    {#each sections as section (section.id)}
      <section class="flex flex-col gap-4">
        <div class="flex justify-between items-end mb-4">
          <h2 class="text-2xl font-bold m-0">{section.title}</h2>
          <button class="bg-transparent border-none text-[#b3b3b3] text-[12px] font-bold cursor-pointer uppercase tracking-[0.1em] hover:underline">Alles tonen</button>
        </div>
        <div class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4 md:gap-6">
          {#each section.tracks.slice(0, 6) as track (track.id)}
            <TrackCard {track} onnavigate={(v) => activeView = v} />
          {/each}
          {#if section.tracks.length === 0}
            <p class="text-[#b3b3b3] col-span-full">Geen tracks gevonden in deze categorie.</p>
          {/if}
        </div>
      </section>
    {/each}
  {:else if activeView === 'songs' || activeView === 'sets' || activeView.startsWith('genre:')}
    <div class="flex flex-col gap-4 mb-6">
        <h2 class="text-2xl font-bold m-0">
            {#if activeView === 'songs' || activeView === 'sets'}
              {$viewMode === 'sets' ? 'Sets' : 'Alle Nummers'}
            {:else}
              {activeView.split(':')[1]}
            {/if}
        </h2>
        <FilterBar view="songs" bind:genre={currentGenre} bind:sort={currentSort} bind:year={currentYear} bind:search={currentTrackSearch} bind:minRating={currentMinRating} bind:includeUnrated={includeUnrated} showGenre={!activeView.startsWith('genre:')} onchange={handleFilterChange} />
    </div>
    {#if isLoading && tracks.length === 0}
        <p>Laden...</p>
    {:else}
        <TrackList {tracks} onnavigate={(v) => activeView = v} />
        {#if tracksHasMore}
            <div class="flex justify-center py-6">
                <button class="bg-transparent border border-[#727272] text-white px-8 py-2 rounded-[24px] font-bold cursor-pointer transition-all hover:border-white hover:scale-[1.04]" onclick={() => loadAllTracks(true)}>Meer laden</button>
            </div>
        {/if}
    {/if}
  {:else if activeView === 'albums'}
    <div class="flex flex-col gap-4 mb-6">
      <h2 class="text-2xl font-bold m-0">Albums</h2>
      <FilterBar view="albums" bind:genre={currentAlbumGenre} bind:sort={currentAlbumSort} bind:search={currentAlbumSearch} onchange={handleFilterChange} />
    </div>
    <div class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4 md:gap-6">
        {#each albums as album (album.id)}
            <div 
              role="button"
              tabindex="0"
              class="bg-[#181818] p-4 rounded-lg flex flex-col gap-3 cursor-pointer transition-colors hover:bg-[#282828]" 
              onclick={() => activeView = `album:${album.id}`}
              onkeydown={(e) => e.key === 'Enter' && (activeView = `album:${album.id}`)}
            >
                <img 
                  src={album.coverArt ? `/rest/getCoverArt?id=${album.coverArt}&size=300&${$authParams}` : '/images/spotify-fallback.svg'} 
                  alt={album.name} 
                  class="w-full aspect-square object-cover rounded shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
                  onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
                />
                <span class="font-bold whitespace-nowrap overflow-hidden text-ellipsis">{album.name}</span>
                <ArtistList 
                  artist={album.artist} 
                  artistId={album.artistId} 
                  artists={album.albumArtists} 
                  onnavigate={(v) => activeView = v} 
                />
            </div>
        {/each}
    </div>
    {#if albumsHasMore}
        <div class="flex justify-center py-6">
            <button class="bg-transparent border border-[#727272] text-white px-8 py-2 rounded-[24px] font-bold cursor-pointer transition-all hover:border-white hover:scale-[1.04]" onclick={() => loadAlbums(true)}>Meer laden</button>
        </div>
    {/if}
  {:else if activeView === 'genres'}
    <div class="flex flex-col gap-4 mb-6">
      <h2 class="text-2xl font-bold m-0">Genres</h2>
    </div>
    {#if isLoading && allGenres.length === 0}
        <p>Laden...</p>
    {:else if allGenres.length === 0}
        <p class="text-[#b3b3b3]">Geen genres gevonden in je bibliotheek.</p>
    {:else}
        <div class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4 md:gap-6">
            {#each allGenres as g}
                <div 
                  role="button"
                  tabindex="0"
                  class="bg-[#181818] p-6 rounded-lg flex flex-col items-center justify-center gap-3 cursor-pointer transition-colors hover:bg-[#282828] aspect-square" 
                  onclick={() => activeView = `genre:${g.value}`}
                  onkeydown={(e) => e.key === 'Enter' && (activeView = `genre:${g.value}`)}
                >
                    <div class="w-16 h-16 rounded-full bg-brand flex items-center justify-center text-black mb-2 shadow-lg">
                        <svg viewBox="0 0 24 24" width="32" height="32" fill="currentColor">
                            <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"></path>
                        </svg>
                    </div>
                    <span class="font-bold text-center break-words w-full">{g.value}</span>
                    <span class="text-xs text-[#b3b3b3]">{g.songCount} nummers</span>
                </div>
            {/each}
        </div>
    {/if}
  {:else if activeView === 'artists'}
    <div class="flex flex-col gap-4 mb-6">
      <h2 class="text-2xl font-bold m-0">Artiesten</h2>
      <FilterBar view="artists" bind:sort={currentArtistSort} bind:role={currentArtistRole} bind:search={currentArtistSearch} onchange={handleFilterChange} />
    </div>
    <div class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4 md:gap-6">
        {#each artists as artist (artist.id)}
            <div 
              role="button"
              tabindex="0"
              class="bg-[#181818] p-4 rounded-lg flex flex-col gap-3 cursor-pointer transition-colors hover:bg-[#282828]" 
              onclick={() => activeView = `artist:${artist.id}`}
              onkeydown={(e) => e.key === 'Enter' && (activeView = `artist:${artist.id}`)}
            >
                <img 
                  src={getArtistImageUrl(artist, $authParams)} 
                  alt={artist.name} 
                  class="w-full aspect-square object-cover rounded-full shadow-[0_8px_24px_rgba(0,0,0,0.5)]" 
                  onerror={(e) => e.target.src = '/images/unknown-artist.svg'}
                />
                <span class="font-bold whitespace-nowrap overflow-hidden text-ellipsis">{artist.name}</span>
                <span class="text-sm text-[#b3b3b3] whitespace-nowrap overflow-hidden text-ellipsis">Artiest</span>
            </div>
        {/each}
    </div>
    {#if artistsHasMore}
        <div class="flex justify-center py-6">
            <button class="bg-transparent border border-[#727272] text-white px-8 py-2 rounded-[24px] font-bold cursor-pointer transition-all hover:border-white hover:scale-[1.04]" onclick={() => loadArtists(true)}>Meer laden</button>
        </div>
    {/if}
  {:else if activeView === 'playlists'}
    <h2 class="text-2xl font-bold m-0 mb-6">Afspeellijsten</h2>
    <div class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4 md:gap-6">
        {#each playlists as playlist (playlist.id)}
            <div 
              role="button"
              tabindex="0"
              class="bg-[#181818] p-4 rounded-lg flex flex-col gap-3 cursor-pointer transition-colors hover:bg-[#282828]" 
              onclick={() => openPlaylist(playlist)}
              onkeydown={(e) => e.key === 'Enter' && openPlaylist(playlist)}
            >
                <img 
                  src={playlist.coverArt ? `/rest/getCoverArt?id=${playlist.coverArt}&size=300&${$authParams}` : '/images/spotify-fallback.svg'} 
                  alt={playlist.name} 
                  class="w-full aspect-square object-cover rounded shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
                  onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
                />
                <span class="font-bold whitespace-nowrap overflow-hidden text-ellipsis">{playlist.name}</span>
            </div>
        {/each}
    </div>
  {:else if activeView === 'playlist-detail'}
    <PlaylistView onnavigate={(v) => activeView = v} />
  {:else if activeView.startsWith('artist:')}
    <ArtistView artistId={activeView.split(':')[1]} onnavigate={(v) => activeView = v} />
  {:else if activeView.startsWith('album:')}
    <AlbumView albumId={activeView.split(':')[1]} onnavigate={(v) => activeView = v} />
  {:else if activeView === 'settings'}
    <Settings />
  {/if}
</div>

<style>
</style>
