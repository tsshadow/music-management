<script>
  import { onMount } from 'svelte';
  import { authParams, playlist, currentTrack, playerState } from './store.js';
  import TrackList from './TrackList.svelte';

  const { onnavigate } = $props();
  let tracks = $state([]);
  let albums = $state([]);
  let artists = $state([]);
  let isLoading = $state(true);

  /**
   * Loads all starred items from the server.
   */
  async function loadStarred() {
    if (!$authParams) return;
    isLoading = true;
    try {
      const response = await fetch(`/rest/getStarred2?${$authParams}`);
      if (response.ok) {
        const data = await response.json();
        const res = data['subsonic-response']?.starred2;
        if (res) {
          const s = res.song || [];
          tracks = Array.isArray(s) ? s : [s];
          
          const al = res.album || [];
          albums = Array.isArray(al) ? al : [al];
          
          const ar = res.artist || [];
          artists = Array.isArray(ar) ? ar : [ar];
        }
      }
    } catch (e) {
      console.error("Failed to load starred items:", e);
    } finally {
      isLoading = false;
    }
  }

  onMount(loadStarred);

  /**
   * Plays all starred songs.
   */
  function playAll() {
    if (tracks.length > 0) {
      playlist.set(tracks);
      currentTrack.set(tracks[0]);
      playerState.update(s => ({ ...s, playing: true }));
    }
  }
</script>

<div class="flex flex-col gap-8 pb-12">
  <header class="flex flex-col md:flex-row items-center md:items-end gap-6 mb-4 text-center md:text-left">
    <div class="w-40 h-40 md:w-52 md:h-52 bg-linear-to-br from-indigo-700 to-indigo-900 shadow-2xl flex items-center justify-center flex-shrink-0">
       <svg viewBox="0 0 24 24" width="80" height="80" fill="white">
         <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"></path>
       </svg>
    </div>
    <div class="flex-1">
      <div class="text-xs font-bold uppercase tracking-wider mb-2">Afspeellijst</div>
      <h1 class="text-4xl md:text-7xl lg:text-8xl font-black mb-6">Favorieten</h1>
      <div class="flex items-center gap-2 text-sm font-medium">
        <span class="text-white">Je favoriete nummers, albums en artiesten</span>
        {#if tracks.length > 0}
          <span class="text-[#b3b3b3]">• {tracks.length} nummers</span>
        {/if}
      </div>
    </div>
  </header>

  <div class="px-2">
     <div class="flex items-center gap-8 mb-8">
       {#if tracks.length > 0}
         <button
           class="bg-brand text-black w-14 h-14 rounded-full flex items-center justify-center shadow-xl hover:scale-105 active:scale-95 transition cursor-pointer border-none"
           onclick={playAll}
           title="Alles afspelen"
         >
           <svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor">
             <path d="M7 6v12l10-6z"></path>
           </svg>
         </button>
       {/if}
     </div>

     {#if isLoading}
        <div class="text-[#b3b3b3] p-12 text-center">Laden...</div>
     {:else}
        {#if tracks.length > 0}
          <section class="mb-12">
            <h2 class="text-2xl font-bold mb-4">Nummers</h2>
            <TrackList {tracks} onnavigate={onnavigate} />
          </section>
        {/if}

        {#if albums.length > 0}
          <section class="mb-12">
            <h2 class="text-2xl font-bold mb-4">Albums</h2>
            <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6">
              {#each albums as album}
                <button 
                  class="bg-[#181818] p-4 rounded-lg hover:bg-[#282828] transition-all group text-left border-none cursor-pointer"
                  onclick={() => onnavigate(`album:${album.id}`)}
                >
                  <div class="relative mb-4 aspect-square shadow-lg">
                    <img 
                      src="/rest/getCoverArt?id={album.coverArt}&size=300&{$authParams}" 
                      alt={album.name}
                      class="w-full h-full object-cover rounded-md"
                      onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
                    />
                  </div>
                  <h3 class="font-bold text-white truncate mb-1">{album.name}</h3>
                  <p class="text-sm text-[#b3b3b3] truncate">{album.artist}</p>
                </button>
              {/each}
            </div>
          </section>
        {/if}

        {#if artists.length > 0}
          <section>
            <h2 class="text-2xl font-bold mb-4">Artiesten</h2>
            <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6">
              {#each artists as artist}
                <button 
                  class="bg-[#181818] p-4 rounded-lg hover:bg-[#282828] transition-all group text-left border-none cursor-pointer"
                  onclick={() => onnavigate(`artist:${artist.id}`)}
                >
                  <div class="relative mb-4 aspect-square shadow-lg">
                    <img 
                      src="/api/artists/{artist.name}/image?{$authParams}" 
                      alt={artist.name}
                      class="w-full h-full object-cover rounded-full"
                      onerror={(e) => e.target.src = '/images/unknown-artist.svg'}
                    />
                  </div>
                  <h3 class="font-bold text-white truncate text-center">{artist.name}</h3>
                </button>
              {/each}
            </div>
          </section>
        {/if}

        {#if tracks.length === 0 && albums.length === 0 && artists.length === 0}
          <div class="text-[#b3b3b3] p-20 text-center flex flex-col items-center gap-4">
            <svg viewBox="0 0 24 24" width="64" height="64" fill="currentColor" class="opacity-20">
              <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"></path>
            </svg>
            <p class="text-xl font-bold text-white">Nog geen favorieten</p>
            <p>Nummers, albums of artiesten die je een hartje geeft komen hier te staan.</p>
          </div>
        {/if}
     {/if}
  </div>
</div>
