<script>
  import { untrack } from 'svelte';
  import { authParams, viewMode } from './store.js';
  import TrackList from './TrackList.svelte';
  import ArtistList from './ArtistList.svelte';

  const { albumId, onnavigate } = $props();

  let album = $state(null);
  let allTracks = $state([]);
  let albumInfo = $state(null);
  let isLoading = $state(true);

  /**
   * Filtered tracks based on viewMode (songs vs sets).
   */
  const tracks = $derived.by(() => {
    if ($viewMode === 'sets') {
      return allTracks.filter(t => t.duration >= 600);
    } else {
      return allTracks.filter(t => t.duration < 600);
    }
  });

  /**
   * Loads the album's details and its tracks.
   */
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
        allTracks = Array.isArray(result) ? result : [result];
        
        loadAlbumInfo();
      }
    } catch (e) {
      console.error(e);
    } finally {
      isLoading = false;
    }
  }

  /**
   * Loads additional album information, such as notes/descriptions.
   */
  async function loadAlbumInfo() {
    try {
      const response = await fetch(`/rest/getAlbumInfo2?id=${albumId}&${$authParams}`);
      const data = await response.json();
      albumInfo = data['subsonic-response']?.albumInfo;
    } catch (e) {
      console.error(e);
    }
  }

  $effect(() => {
    const id = albumId;
    const auth = $authParams;
    if (id && auth) {
      untrack(() => loadAlbum());
    }
  });

  /**
   * Navigates to the artist detail view for the album's primary artist.
   */
  function openArtist() {
     const id_to_use = album.artistId || (tracks.length > 0 ? tracks[0].artistId : null);
     if (id_to_use && onnavigate) onnavigate(`artist:${id_to_use}`);
  }
</script>

{#if isLoading}
  <div class="p-8">Laden...</div>
{:else if album}
  <div class="flex flex-col">
    <header class="h-auto md:h-[340px] flex flex-col md:flex-row items-center md:items-end p-6 md:p-8 bg-linear-to-b from-transparent to-black/50 relative gap-6 text-center md:text-left">
       <img 
         src={album.coverArt ? `/rest/getCoverArt?id=${album.coverArt}&size=300&${$authParams}` : '/images/spotify-fallback.svg'} 
         alt={album.name} 
         class="w-[160px] h-[160px] md:w-[232px] md:h-[232px] object-cover shadow-[0_4px_60px_rgba(0,0,0,0.5)]"
         onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
       />
       <div class="flex flex-col">
         <div class="uppercase text-xs font-bold">Album</div>
         <h1 class="text-3xl md:text-5xl lg:text-7xl font-black my-2 leading-tight md:leading-none">{album.name}</h1>
         <div class="flex flex-wrap items-center justify-center md:justify-start gap-1 font-bold">
            <ArtistList 
              artist={album.artist} 
              artistId={album.artistId} 
              artists={album.albumArtists} 
              onnavigate={onnavigate} 
            />
            {#if album.year} <span class="text-[#b3b3b3] hidden md:inline">•</span> {album.year}{/if}
            {#if tracks.length > 0} <span class="text-[#b3b3b3]">•</span> {tracks.length} nummers{/if}
         </div>
       </div>
    </header>

    <div class="p-6 md:p-8 pt-0">
      {#if tracks.length > 0}
        <TrackList {tracks} onnavigate={onnavigate} />
      {:else}
        <div class="text-[#b3b3b3] p-12 text-center border border-white/5 rounded-xl bg-white/5">
          <p class="text-xl font-bold mb-2 text-white">Geen {$viewMode === 'sets' ? 'sets' : 'nummers'} gevonden</p>
          <p class="text-sm opacity-60">Dit album bevat geen items die overeenkomen met de huidige {$viewMode === 'sets' ? 'sets' : 'nummers'} weergave.</p>
        </div>
      {/if}
      
      {#if album.genre || album.created}
        <div class="text-[#b3b3b3] text-sm mt-8 space-y-1">
            {#if album.genre}<div>Genre: {album.genre}</div>{/if}
            {#if album.created}<div>Toegevoegd op {new Date(album.created).toLocaleDateString()}</div>{/if}
        </div>
      {/if}

      {#if albumInfo && albumInfo.notes}
        <div class="mt-8 border-t border-[#282828] pt-8">
            <h3 class="text-xl font-bold mb-4">Over dit album</h3>
            <p class="text-[#b3b3b3] whitespace-pre-wrap">{albumInfo.notes}</p>
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
</style>
