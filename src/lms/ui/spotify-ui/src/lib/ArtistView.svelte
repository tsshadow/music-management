<script>
  import { authParams } from './store.js';
  import TrackList from './TrackList.svelte';

  const { artistId, onnavigate } = $props();

  let artist = $state(null);
  let albums = $state([]);
  let appearsOn = $state([]);
  let tracks = $state([]);
  let similarArtists = $state([]);
  let isLoading = $state(true);

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

  $effect(() => {
    if (artistId && $authParams) {
      loadArtist();
    }
  });

  function openAlbum(id) {
    if (onnavigate) onnavigate(`album:${id}`);
  }

  function openArtist(id) {
    if (onnavigate) onnavigate(`artist:${id}`);
  }
</script>

{#if isLoading}
  <div class="p-8">Laden...</div>
{:else if artist}
  <div class="flex flex-col">
    <header class="h-[340px] flex items-end p-6 md:p-8 bg-linear-to-b from-transparent to-black/50 relative gap-6">
       <div class="w-[232px] h-[232px] flex-shrink-0">
         {#if artist.coverArt}
           <img src="/rest/getCoverArt?id={artist.coverArt}&size=300&${$authParams}" alt={artist.name} class="w-full h-full object-cover rounded-full shadow-[0_4px_60px_rgba(0,0,0,0.5)]" />
         {:else}
           <div class="w-full h-full bg-[#282828] rounded-full flex items-center justify-center shadow-[0_4px_60px_rgba(0,0,0,0.5)]">
             <img src="/images/spotify-fallback.svg" alt="" class="w-24 h-24 opacity-20" />
           </div>
         {/if}
       </div>
       <div class="flex flex-col">
         <div class="flex items-center gap-2 text-sm font-bold mb-2">
            <svg viewBox="0 0 24 24" width="24" height="24" fill="#3d91f4">
                <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2zM10 17l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"></path>
            </svg>
            Geverifieerde artiest
         </div>
         <h1 class="text-6xl md:text-8xl lg:text-9xl font-black m-0 leading-none">{artist.name}</h1>
       </div>
    </header>

    <div class="p-6 md:p-8 flex flex-col gap-8">
        {#if tracks.length > 0}
            <section>
                <h2 class="text-2xl font-bold mb-4">Populair</h2>
                <TrackList {tracks} onnavigate={onnavigate} />
            </section>
        {/if}

        {#if albums.length > 0}
            <section>
                <h2 class="text-2xl font-bold mb-4">Discografie</h2>
                <div class="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-6">
                    {#each albums as album (album.id)}
                        <div 
                          role="button"
                          tabindex="0"
                          class="bg-[#181818] p-4 rounded-lg transition-colors cursor-pointer hover:bg-[#282828]" 
                          onclick={() => openAlbum(album.id)}
                          onkeydown={(e) => e.key === 'Enter' && openAlbum(album.id)}
                        >
                            <img 
                              src={album.coverArt ? `/rest/getCoverArt?id=${album.id}&size=300&${$authParams}` : '/images/spotify-fallback.svg'} 
                              alt={album.name} 
                              class="w-full aspect-square object-cover mb-4 rounded shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
                              onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
                            />
                            <span class="block font-bold mb-1 whitespace-nowrap overflow-hidden text-ellipsis">{album.name}</span>
                            <span class="text-sm text-[#b3b3b3]">{album.year || ''} • Album</span>
                        </div>
                    {/each}
                </div>
            </section>
        {/if}

        {#if appearsOn.length > 0}
            <section>
                <h2 class="text-2xl font-bold mb-4">Komt voor op</h2>
                <div class="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-6">
                    {#each appearsOn as album (album.id)}
                        <div 
                          role="button"
                          tabindex="0"
                          class="bg-[#181818] p-4 rounded-lg transition-colors cursor-pointer hover:bg-[#282828]" 
                          onclick={() => openAlbum(album.id)}
                          onkeydown={(e) => e.key === 'Enter' && openAlbum(album.id)}
                        >
                            <img 
                              src={album.coverArt ? `/rest/getCoverArt?id=${album.id}&size=300&${$authParams}` : '/images/spotify-fallback.svg'} 
                              alt={album.name} 
                              class="w-full aspect-square object-cover mb-4 rounded shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
                              onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
                            />
                            <span class="block font-bold mb-1 whitespace-nowrap overflow-hidden text-ellipsis">{album.name}</span>
                            <span class="text-sm text-[#b3b3b3]">{album.artist}</span>
                        </div>
                    {/each}
                </div>
            </section>
        {/if}

        {#if similarArtists.length > 0}
            <section>
                <h2 class="text-2xl font-bold mb-4">Fans vinden dit ook leuk</h2>
                <div class="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-6">
                    {#each similarArtists as similar (similar.id)}
                        <div 
                          role="button"
                          tabindex="0"
                          class="bg-[#181818] p-4 rounded-lg transition-colors cursor-pointer hover:bg-[#282828]" 
                          onclick={() => openArtist(similar.id)}
                          onkeydown={(e) => e.key === 'Enter' && openArtist(similar.id)}
                        >
                            <div class="mb-4">
                                <img 
                                  src={similar.coverArt ? `/rest/getCoverArt?id=${similar.coverArt}&size=300&${$authParams}` : '/images/spotify-fallback.svg'} 
                                  alt={similar.name} 
                                  class="w-full aspect-square object-cover rounded-full shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
                                  onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
                                />
                            </div>
                            <span class="block font-bold mb-1 whitespace-nowrap overflow-hidden text-ellipsis">{similar.name}</span>
                            <span class="text-sm text-[#b3b3b3]">Artiest</span>
                        </div>
                    {/each}
                </div>
            </section>
        {/if}
    </div>
  </div>
{/if}

<style>
</style>
