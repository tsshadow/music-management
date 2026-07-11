<script>
  import { untrack } from 'svelte';
  import { authParams, viewMode, deduplicateEnabled } from './store.js';
  import { getArtistImageUrl } from './utils.js';
  import { deduplicateTracks, getDeduplicateKey } from './deduplicate.js';
  import TrackList from './TrackList.svelte';

  const { artistId, onnavigate } = $props();

  let artist = $state(null);
  let albumGroups = $state({});
  let appearsOn = $state([]);
  let similarArtists = $state([]);
  let allTracks = $state([]);
  let allTracksOffset = $state(0);
  let allTracksHasMore = $state(false);
  let seenKeys = new Map();
  let biography = $state("");
  let mbid = $state("");
  let isLoading = $state(true);

  /**
   * Toggles the starred status of the artist.
   */
  async function toggleStar() {
    if (!artist) return;
    const isCurrentlyStarred = !!artist.starred;
    const endpoint = isCurrentlyStarred ? 'unstar' : 'star';
    
    // Optimistic update
    if (isCurrentlyStarred) delete artist.starred;
    else artist.starred = new Date().toISOString();

    try {
      const response = await fetch(`/rest/${endpoint}?artistId=${artistId}&${$authParams}`);
      if (!response.ok) throw new Error('Failed to toggle star');
    } catch (e) {
      console.error(e);
      // Rollback
      if (isCurrentlyStarred) artist.starred = new Date().toISOString();
      else delete artist.starred;
    }
  }

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

        const groups = {};
        const other = [];

        allAlbums.forEach(a => {
          if (a.artist === artistData.name) {
            const type = (a.releaseTypes && a.releaseTypes.length > 0) ? a.releaseTypes[0] : 'Album';
            if (!groups[type]) groups[type] = [];
            groups[type].push(a);
          } else {
            other.push(a);
          }
        });

        albumGroups = groups;
        appearsOn = other;

        loadAllTracks();
        loadArtistInfo();
        loadArtistMuma();
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
        allTracksHasMore = true;
        seenKeys = new Map();
    }
    const pageSize = append ? 100 : 25;
    const durationFilter = $viewMode === 'sets' ? 'minDuration=10' : 'maxDuration=10';
    
    let currentBatch = [];
    try {
      while (currentBatch.length < pageSize && allTracksHasMore) {
        let url = `/rest/getSpotifyTracks?artistId=${artistId}&offset=${allTracksOffset}&count=${pageSize}&${durationFilter}&sort=recent&${$authParams}`;
        if ($deduplicateEnabled) url += `&deduplicate=true`;
        const response = await fetch(url);
        const data = await response.json();
        const tracksNode = data['subsonic-response']?.tracks;
        const result = tracksNode?.track || [];
        const newTracks = Array.isArray(result) ? result : [result];

        const deduped = $deduplicateEnabled ? deduplicateTracks(newTracks, seenKeys) : newTracks;
        if ($deduplicateEnabled) {
          for (const track of deduped) {
            seenKeys.set(getDeduplicateKey(track), track);
          }
        }

        currentBatch.push(...deduped);
        allTracksHasMore = tracksNode?.moreResults === true || tracksNode?.moreResults === "true";
        allTracksOffset = tracksNode?.nextOffset !== undefined ? tracksNode.nextOffset : (allTracksOffset + newTracks.length);

        if (!allTracksHasMore || currentBatch.length >= pageSize) break;
      }

      if (append) {
          allTracks = [...allTracks, ...currentBatch];
      } else {
          allTracks = currentBatch;
      }
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
      const info = data['subsonic-response']?.artistInfo || data['subsonic-response']?.artistInfo2;
      if (info) {
        if (info.similarArtist) {
          similarArtists = Array.isArray(info.similarArtist) ? info.similarArtist : [info.similarArtist];
        }
        if (info.biography) {
          biography = info.biography;
        }
        if (info.musicBrainzId) {
          mbid = info.musicBrainzId;
        }
      } else {
        similarArtists = [];
        biography = "";
        mbid = "";
      }
    } catch (e) {
      console.error(e);
    }
  }

  /**
   * Loads artist genres from MuMa API.
   */
  async function loadArtistMuma() {
    try {
      const response = await fetch(`/api/artists/${artistId}?${$authParams}`);
      if (response.ok) {
        const data = await response.json();
        if (data && data.genres) {
           artist.genres = data.genres;
        }
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
         <div class="flex flex-wrap items-center justify-center md:justify-start gap-4 mt-6">
           <button 
             class="w-12 h-12 md:w-14 md:h-14 bg-brand rounded-full flex items-center justify-center hover:scale-105 transition-transform shadow-lg border-none cursor-pointer"
             onclick={() => {
                if (allTracks.length > 0) {
                  currentTrack.set(allTracks[0]);
                  playlist.set(allTracks);
                  playerState.update(s => ({ ...s, playing: true }));
                }
             }}
             aria-label="Afspelen"
           >
              <svg viewBox="0 0 24 24" width="24" height="24" fill="black">
                <path d="M7 6v12l10-6z"></path>
              </svg>
           </button>

           <button 
             class="w-10 h-10 md:w-12 md:h-12 bg-transparent border border-white/20 rounded-full flex items-center justify-center hover:border-white hover:scale-105 transition-all cursor-pointer text-[#b3b3b3] hover:text-white"
             onclick={() => {
                if (allTracks.length > 0) {
                  const shuffled = [...allTracks].sort(() => Math.random() - 0.5);
                  currentTrack.set(shuffled[0]);
                  playlist.set(shuffled);
                  playerState.update(s => ({ ...s, playing: true, shuffle: true }));
                }
             }}
             title="Shuffle afspelen"
           >
              <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                <path d="M10.59 9.17L5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.45 20 9.5V4h-5.5zm.33 9.41l-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z"></path>
              </svg>
           </button>

           <button 
             class="bg-transparent border-none p-0 cursor-pointer transition-transform hover:scale-110 {artist.starred ? 'text-brand' : 'text-[#b3b3b3] hover:text-white'}"
             onclick={toggleStar}
             title={artist.starred ? "Verwijderen uit favorieten" : "Toevoegen aan favorieten"}
           >
              {#if artist.starred}
                <svg viewBox="0 0 24 24" width="32" height="32" fill="currentColor">
                  <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"></path>
                </svg>
              {:else}
                <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"></path>
                </svg>
              {/if}
           </button>
         </div>
         {#if artist.genres}
           <div class="flex flex-wrap gap-2 mt-4">
             {#each (Array.isArray(artist.genres) ? artist.genres : [artist.genres]) as genre}
               <span class="px-3 py-1 bg-white/10 hover:bg-white/20 rounded-full text-xs font-bold transition-colors cursor-default border border-white/5">
                 {genre.name}
               </span>
             {/each}
           </div>
         {/if}
       </div>
    </header>

    <div class="p-6 md:p-8 flex flex-col gap-8">
        {#if biography || mbid}
            <section>
                <h2 class="text-2xl font-bold mb-4">Over {artist.name}</h2>
                <div class="bg-[#181818] rounded-xl p-6 md:p-8 relative overflow-hidden group">
                    <div class="relative z-10 max-w-3xl">
                        {#if biography}
                            <p class="text-[#b3b3b3] text-sm md:text-base leading-relaxed line-clamp-6 group-hover:line-clamp-none transition-all duration-500 whitespace-pre-wrap mb-4">
                                {biography}
                            </p>
                        {/if}
                        {#if mbid}
                            <a 
                                href="https://musicbrainz.org/artist/{mbid}" 
                                target="_blank" 
                                rel="noopener noreferrer"
                                class="inline-flex items-center gap-2 text-xs font-bold text-[#b3b3b3] hover:text-white transition-colors"
                            >
                                <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"></path>
                                </svg>
                                Bekijk op MusicBrainz
                            </a>
                        {/if}
                    </div>
                    <div class="absolute inset-0 bg-linear-to-t from-black/20 to-transparent pointer-events-none"></div>
                </div>
            </section>
        {/if}

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

        {#each Object.entries(albumGroups).sort() as [type, groupAlbums]}
            <section>
                <h2 class="text-2xl font-bold mb-4">{type}s</h2>
                <div class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4 md:gap-6">
                    {#each groupAlbums as album (album.id)}
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
                            <span class="text-sm text-[#b3b3b3]">{album.year || ''} • {type}</span>
                        </div>
                    {/each}
                </div>
            </section>
        {/each}

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
                                  src={getArtistImageUrl(similar, $authParams)}
                                  alt={similar.name}
                                  class="w-full aspect-square object-cover rounded-full shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
                                  onerror={(e) => e.target.src = '/images/unknown-artist.svg'}
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
