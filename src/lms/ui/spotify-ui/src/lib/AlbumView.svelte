<script>
  import { onMount } from 'svelte';
  import { authParams } from './store.js';
  import TrackList from './TrackList.svelte';

  export let albumId;
  export let onNavigate;

  let album = null;
  let tracks = [];
  let albumInfo = null;
  let isLoading = true;

  async function loadAlbum() {
    if (!$authParams) return;
    isLoading = true;
    try {
      const response = await fetch(`/rest/getAlbum?id=${albumId}&${$authParams}`);
      const data = await response.json();
      const albumData = data['subsonic-response']?.album;
      if (albumData) {
        album = albumData;
        const result = albumData.song || [];
        tracks = Array.isArray(result) ? result : [result];
        
        loadAlbumInfo();
      }
    } catch (e) {
      console.error(e);
    } finally {
      isLoading = false;
    }
  }

  async function loadAlbumInfo() {
    try {
      const response = await fetch(`/rest/getAlbumInfo2?id=${albumId}&${$authParams}`);
      const data = await response.json();
      albumInfo = data['subsonic-response']?.albumInfo;
    } catch (e) {
      console.error(e);
    }
  }

  onMount(loadAlbum);

  function openArtist() {
     const id_to_use = album.artistId || (tracks.length > 0 ? tracks[0].artistId : null);
     if (id_to_use) onNavigate(`artist:${id_to_use}`);
  }
</script>

{#if isLoading}
  <div class="p-8">Laden...</div>
{:else if album}
  <div class="album-view">
    <header class="album-header">
       <img 
         src="/rest/getCoverArt?id={album.id}&size=300&${$authParams}" 
         alt={album.name} 
         on:error={(e) => e.target.src = '/images/spotify-fallback.svg'}
       />
       <div class="info">
         <div class="type uppercase text-xs font-bold">Album</div>
         <h1>{album.name}</h1>
         <div class="meta flex items-center gap-1 font-bold">
            <span class="artist-link cursor-pointer hover:underline" on:click={openArtist}>{album.artist}</span>
            {#if album.year} <span class="text-spotify-text">•</span> {album.year}{/if}
            {#if tracks.length > 0} <span class="text-spotify-text">•</span> {tracks.length} nummers{/if}
         </div>
       </div>
    </header>

    <div class="tracklist-container p-8 pt-0">
      <TrackList {tracks} on:navigate={(e) => onNavigate(e.detail)} />
      
      {#if album.genre || album.created}
        <div class="footer-meta text-spotify-text text-sm mt-8 space-y-1">
            {#if album.genre}<div>Genre: {album.genre}</div>{/if}
            {#if album.created}<div>Toegevoegd op {new Date(album.created).toLocaleDateString()}</div>{/if}
        </div>
      {/if}

      {#if albumInfo && albumInfo.notes}
        <div class="extra-info mt-8 border-t border-spotify-light pt-8">
            <h3 class="text-xl font-bold mb-4">Over dit album</h3>
            <p class="text-spotify-text whitespace-pre-wrap">{albumInfo.notes}</p>
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .album-header {
    height: 340px;
    display: flex;
    align-items: flex-end;
    padding: 24px 32px;
    background: linear-gradient(transparent, rgba(0,0,0,0.5));
    gap: 24px;
  }
  .album-header img {
    width: 232px;
    height: 232px;
    box-shadow: 0 4px 60px rgba(0,0,0,.5);
    object-fit: cover;
  }
  h1 {
    font-size: 72px;
    margin: 8px 0;
    font-weight: 900;
    line-height: 1;
  }
</style>
