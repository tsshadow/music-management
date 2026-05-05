<script>
  import { onMount } from 'svelte';
  import { authParams } from './store.js';
  import TrackList from './TrackList.svelte';

  export let artistId;
  export let onNavigate;

  let artist = null;
  let albums = [];
  let appearsOn = [];
  let tracks = [];
  let similarArtists = [];
  let isLoading = true;

  async function loadArtist() {
    if (!$authParams) return;
    isLoading = true;
    try {
      const response = await fetch(`/rest/getArtist?id=${artistId}&${$authParams}`);
      const data = await response.json();
      const artistData = data['subsonic-response']?.artist;
      if (artistData) {
        artist = artistData;
        const allAlbums = Array.isArray(artistData.album) ? artistData.album : (artistData.album ? [artistData.album] : []);
        
        // In Subsonic getArtist, "album" array contains both main albums and albums where artist appears.
        // We try to distinguish them if possible. 
        // Simple heuristic: if album.artist === artist.name, it's a main album.
        albums = allAlbums.filter(a => a.artist === artist.name);
        appearsOn = allAlbums.filter(a => a.artist !== artist.name);
        
        loadTopTracks();
        loadArtistInfo();
      }
    } catch (e) {
      console.error(e);
    } finally {
      isLoading = false;
    }
  }

  async function loadTopTracks() {
    try {
      const response = await fetch(`/rest/getTopSongs?artist=${encodeURIComponent(artist.name)}&count=5&${$authParams}`);
      const data = await response.json();
      const result = data['subsonic-response']?.topSongs?.song || [];
      tracks = Array.isArray(result) ? result : [result];
    } catch (e) {
      console.error(e);
    }
  }

  async function loadArtistInfo() {
    try {
      const response = await fetch(`/rest/getArtistInfo2?id=${artistId}&${$authParams}`);
      const data = await response.json();
      const info = data['subsonic-response']?.artistInfo;
      if (info && info.similarArtist) {
        similarArtists = Array.isArray(info.similarArtist) ? info.similarArtist : [info.similarArtist];
      }
    } catch (e) {
      console.error(e);
    }
  }

  onMount(loadArtist);

  function openAlbum(id) {
    onNavigate(`album:${id}`);
  }

  function openArtist(id) {
    onNavigate(`artist:${id}`);
  }
</script>

{#if isLoading}
  <div class="p-8">Laden...</div>
{:else if artist}
  <div class="artist-view">
    <header class="artist-header">
       <div class="cover-wrapper">
         {#if artist.coverArt}
           <img src="/rest/getCoverArt?id={artist.coverArt}&size=300&${$authParams}" alt={artist.name} />
         {:else}
           <div class="fallback">
             <img src="/images/spotify-fallback.svg" alt="" class="w-24 h-24 opacity-20" />
           </div>
         {/if}
       </div>
       <div class="info">
         <div class="verified">
            <svg viewBox="0 0 24 24" width="24" height="24" fill="#3d91f4">
                <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2zM10 17l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"></path>
            </svg>
            Geverifieerde artiest
         </div>
         <h1>{artist.name}</h1>
       </div>
    </header>

    <div class="content p-8">
        {#if tracks.length > 0}
            <section class="mb-8">
                <h2 class="text-2xl font-bold mb-4">Populair</h2>
                <TrackList {tracks} on:navigate={(e) => onNavigate(e.detail)} />
            </section>
        {/if}

        {#if albums.length > 0}
            <section class="mb-8">
                <h2 class="text-2xl font-bold mb-4">Discografie</h2>
                <div class="grid">
                    {#each albums as album}
                        <div class="card" on:click={() => openAlbum(album.id)}>
                            <img 
                              src={album.coverArt ? `/rest/getCoverArt?id=${album.id}&size=300&${$authParams}` : '/images/spotify-fallback.svg'} 
                              alt={album.name} 
                              on:error={(e) => e.target.src = '/images/spotify-fallback.svg'}
                            />
                            <span class="title">{album.name}</span>
                            <span class="artist">{album.year || ''} • Album</span>
                        </div>
                    {/each}
                </div>
            </section>
        {/if}

        {#if appearsOn.length > 0}
            <section class="mb-8">
                <h2 class="text-2xl font-bold mb-4">Komt voor op</h2>
                <div class="grid">
                    {#each appearsOn as album}
                        <div class="card" on:click={() => openAlbum(album.id)}>
                            <img 
                              src={album.coverArt ? `/rest/getCoverArt?id=${album.id}&size=300&${$authParams}` : '/images/spotify-fallback.svg'} 
                              alt={album.name} 
                              on:error={(e) => e.target.src = '/images/spotify-fallback.svg'}
                            />
                            <span class="title">{album.name}</span>
                            <span class="artist">{album.artist}</span>
                        </div>
                    {/each}
                </div>
            </section>
        {/if}

        {#if similarArtists.length > 0}
            <section class="mb-8">
                <h2 class="text-2xl font-bold mb-4">Fans vinden dit ook leuk</h2>
                <div class="grid">
                    {#each similarArtists as similar}
                        <div class="card artist-card" on:click={() => openArtist(similar.id)}>
                            <div class="img-wrapper">
                                <img 
                                  src={similar.coverArt ? `/rest/getCoverArt?id=${similar.coverArt}&size=300&${$authParams}` : '/images/spotify-fallback.svg'} 
                                  alt={similar.name} 
                                  on:error={(e) => e.target.src = '/images/spotify-fallback.svg'}
                                />
                            </div>
                            <span class="title">{similar.name}</span>
                            <span class="artist">Artiest</span>
                        </div>
                    {/each}
                </div>
            </section>
        {/if}
    </div>
  </div>
{/if}

<style>
  .artist-header {
    height: 340px;
    display: flex;
    align-items: flex-end;
    padding: 24px 32px;
    background: linear-gradient(transparent, rgba(0,0,0,0.5));
    position: relative;
    gap: 24px;
  }
  .cover-wrapper {
    width: 232px;
    height: 232px;
    flex-shrink: 0;
  }
  .cover-wrapper img, .cover-wrapper .fallback {
    width: 100%;
    height: 100%;
    object-fit: cover;
    border-radius: 50%;
    box-shadow: 0 4px 60px rgba(0,0,0,.5);
  }
  .cover-wrapper .fallback {
      background-color: #282828;
      display: flex;
      align-items: center;
      justify-content: center;
  }
  .info .verified {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 14px;
      font-weight: 700;
      margin-bottom: 8px;
  }
  h1 {
    font-size: 96px;
    font-weight: 900;
    margin: 0;
    line-height: 1;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 24px;
  }
  .card {
    background: #181818;
    padding: 16px;
    border-radius: 8px;
    transition: background 0.3s;
    cursor: pointer;
  }
  .card:hover {
    background: #282828;
  }
  .card img {
    width: 100%;
    aspect-ratio: 1/1;
    object-fit: cover;
    margin-bottom: 16px;
    border-radius: 4px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.5);
  }
  .artist-card .img-wrapper img {
      border-radius: 50%;
  }
  .card .title {
    display: block;
    font-weight: 700;
    margin-bottom: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .card .artist {
    font-size: 14px;
    color: #b3b3b3;
  }
</style>
