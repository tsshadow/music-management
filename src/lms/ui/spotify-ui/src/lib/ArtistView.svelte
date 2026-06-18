<script>
  import { untrack } from 'svelte';
  import { authParams, viewMode } from './store.js';
  import { getArtistImageUrl } from './utils.js';
  import TrackList from './TrackList.svelte';

  const { artistId, onnavigate } = $props();

  let artist = $state(null);
  let albums = $state([]);
  let appearsOn = $state([]);
  let similarArtists = $state([]);
  let allTracks = $state([]);
  let allTracksOffset = $state(0);
  let allTracksHasMore = $state(false);
  let isLoading = $state(true);

  /**
   * Loads the artist's basic data and triggers related content loading.
   */
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
        
        albums = allAlbums.filter(a => a.artist === artistData.name);
        appearsOn = allAlbums.filter(a => a.artist !== artistData.name);
        
        loadAllTracks();
        loadArtistInfo();
      }
    } catch (e) {
      console.error(e);
    } finally {
      isLoading = false;
    }
  }

  /**
   * Loads all tracks by the artist, filtered by duration based on viewMode.
   * 
   * @param {boolean} [append=false] - Whether to append new results to the existing tracks.
   */
  async function loadAllTracks(append = false) {
    if (!append) {
        allTracksOffset = 0;
        allTracksHasMore = false;
    }
    const count = append ? 100 : 25;
    const durationFilter = $viewMode === 'sets' ? 'minDuration=10' : 'maxDuration=10';
    try {
      const response = await fetch(`/rest/getSpotifyTracks?artistId=${artistId}&offset=${allTracksOffset}&count=${count}&${durationFilter}&sort=recent&${$authParams}`);
      const data = await response.json();
      const tracksNode = data['subsonic-response']?.tracks;
      const result = tracksNode?.track || [];
      const newTracks = Array.isArray(result) ? result : [result];
      
      if (append) {
          allTracks = [...allTracks, ...newTracks];
      } else {
          allTracks = newTracks;
      }
      
      allTracksOffset += newTracks.length;
      allTracksHasMore = tracksNode?.moreResults === true || tracksNode?.moreResults === "true";
    } catch (e) {
      console.error(e);
    }
  }

  /**
   * Loads additional artist information, such as similar artists.
   */
  async function loadArtistInfo() {
    try {
      const response = await fetch(`/rest/getArtistInfo2?id=${artistId}&${$authParams}`);
      const data = await response.json();
      const info = data['subsonic-response']?.artistInfo;
      if (info && info.similarArtist) {
        similarArtists = Array.isArray(info.similarArtist) ? info.similarArtist : [info.similarArtist];
      } else {
        similarArtists = [];
      }
    } catch (e) {
      console.error(e);
    }
  }

  $effect(() => {
    const id = artistId;
    const auth = $authParams;
    const mode = $viewMode;
    if (id && auth) {
      untrack(() => loadArtist());
    }
  });

  /**
   * Navigates to a specific album detail view.
   * 
   * @param {string} id - The Subsonic album ID.
   */
  function openAlbum(id) {
    if (onnavigate) onnavigate(`album:${id}`);
  }

  /**
   * Navigates to a specific artist detail view.
   * 
   * @param {string} id - The Subsonic artist ID.
   */
  function openArtist(id) {
    if (onnavigate) onnavigate(`artist:${id}`);
  }
</script>

{#if isLoading}
  <div class="p-8">Laden...</div>
{:else if artist}
  <div class="flex flex-col">
    <header class="h-auto md:h-[340px] flex flex-col md:flex-row items-center md:items-end p-6 md:p-8 bg-linear-to-b from-transparent to-black/50 relative gap-6 text-center md:text-left">
       <div class="w-[160px] h-[160px] md:w-[232px] md:h-[232px] flex-shrink-0">
         <img 
           src={getArtistImageUrl(artist, $authParams)} 
           alt={artist.name} 
           class="w-full h-full object-cover rounded-full shadow-[0_4px_60px_rgba(0,0,0,0.5)]"
           onerror={(e) => e.target.src = '/images/unknown-artist.svg'}
         />
       </div>
       <div class="flex flex-col">
         <div class="flex items-center justify-center md:justify-start gap-2 text-sm font-bold mb-2">
            <svg viewBox="0 0 24 24" width="24" height="24" fill="#3d91f4">
                <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2zM10 17l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"></path>
            </svg>
            Geverifieerde artiest
         </div>
         <h1 class="text-4xl md:text-7xl lg:text-9xl font-black m-0 leading-tight md:leading-none">{artist.name}</h1>
       </div>
    </header>

    <div class="p-6 md:p-8 flex flex-col gap-8">
        <section>
            <h2 class="text-2xl font-bold mb-4">{$viewMode === 'sets' ? 'Alle sets' : 'Alle nummers'}</h2>
            {#if allTracks.length > 0}
                <TrackList tracks={allTracks} onnavigate={onnavigate} />
                {#if allTracksHasMore}
                    <div class="flex justify-center py-4">
                        <button class="bg-transparent border border-[#727272] text-white px-8 py-2 rounded-[24px] font-bold cursor-pointer transition-all hover:border-white hover:scale-[1.04]" onclick={() => loadAllTracks(true)}>Meer laden</button>
                    </div>
                {/if}
            {:else}
                <div class="text-[#b3b3b3] p-12 text-center border border-white/5 rounded-xl bg-white/5">
                    <p class="text-xl font-bold mb-2 text-white">Geen {$viewMode === 'sets' ? 'sets' : 'nummers'} gevonden</p>
                    <p class="text-sm opacity-60">Deze artiest heeft geen items die overeenkomen met de huidige {$viewMode === 'sets' ? 'sets' : 'nummers'} weergave.</p>
                </div>
            {/if}
        </section>

        {#if albums.length > 0}
            <section>
                <h2 class="text-2xl font-bold mb-4">Discografie</h2>
                <div class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4 md:gap-6">
                    {#each albums as album (album.id)}
                        <div 
                          role="button"
                          tabindex="0"
                          class="bg-[#181818] p-4 rounded-lg transition-colors cursor-pointer hover:bg-[#282828]" 
                          onclick={() => openAlbum(album.id)}
                          onkeydown={(e) => e.key === 'Enter' && openAlbum(album.id)}
                        >
                            <img 
                              src={album.coverArt ? `/rest/getCoverArt?id=${album.coverArt}&size=300&${$authParams}` : '/images/spotify-fallback.svg'} 
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
                <div class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4 md:gap-6">
                    {#each appearsOn as album (album.id)}
                        <div 
                          role="button"
                          tabindex="0"
                          class="bg-[#181818] p-4 rounded-lg transition-colors cursor-pointer hover:bg-[#282828]" 
                          onclick={() => openAlbum(album.id)}
                          onkeydown={(e) => e.key === 'Enter' && openAlbum(album.id)}
                        >
                            <img 
                              src={album.coverArt ? `/rest/getCoverArt?id=${album.coverArt}&size=300&${$authParams}` : '/images/spotify-fallback.svg'} 
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
                <div class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4 md:gap-6">
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
