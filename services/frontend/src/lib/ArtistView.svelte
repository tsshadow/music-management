<script>
  import { t } from './i18n/index.js';
  import { untrack } from 'svelte';
  import { SvelteMap } from 'svelte/reactivity';
  import { authParams, viewMode, deduplicateEnabled, mumaApiUrl, currentTrack, playerState, hasPermission, restUrl } from './store.js';
  import { getArtistImageUrl } from './utils.js';
  import { getHeaders } from './mumaApi.js';
  import { Pencil } from '@lucide/svelte';
  import { deduplicateTracks, getDeduplicateKey } from './deduplicate.js';
  import TrackList from './TrackList.svelte';
  import { listOf, subsonicJson } from './subsonic.js';
  import { recordPlace } from './recentPlaces.js';
  import { startQueue } from './queue.js';

  const { artistId, onnavigate } = $props();

  let artist = $state(null);
  let albumGroups = $state({});
  let appearsOn = $state([]);
  let similarArtists = $state([]);
  let allTracks = $state([]);
  let allTracksOffset = $state(0);
  let allTracksHasMore = $state(false);
  let seenKeys = new SvelteMap();
  let biography = $state("");
  let mbid = $state("");
  let isLoading = $state(true);
  let loadFailed = $state(false);
  // Which load is current. Every answer checks it before it writes anything, so the answer for
  // an artist the listener already left can never land on the page of the one they went to.
  let loadSeq = 0;

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
      const response = await fetch(restUrl(`/rest/${endpoint}?artistId=${artistId}&${$authParams}`));
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
    const seq = ++loadSeq;
    isLoading = true;
    loadFailed = false;
    // Nothing of the previous artist survives into this one, whatever fails below.
    artist = null;
    albumGroups = {};
    appearsOn = [];
    similarArtists = [];
    allTracks = [];
    biography = "";
    mbid = "";
    try {
      const data = await subsonicJson('getArtist', { id: artistId });
      if (seq !== loadSeq) return;
      const artistData = data['subsonic-response']?.artist;
      if (!artistData) loadFailed = true;
      if (artistData) {
        artist = artistData;
        // The place is opened before this resolves (App's handleNavigate records the bare
        // 'artist:<id>'); this backfills the name once it is known.
        recordPlace(`artist:${artistId}`, artistData.name);
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

        loadAllTracks(false, seq);
        loadArtistInfo(seq);
        loadArtistMuma(seq);
      }
    } catch (e) {
      if (seq !== loadSeq) return;
      console.error(e);
      loadFailed = true;
    } finally {
      if (seq === loadSeq) isLoading = false;
    }
  }

  /**
   * Loads all tracks by the artist, filtered by duration based on viewMode.
   *
   * @param {boolean} [append=false] - Whether to append new results to the existing tracks.
   * @param {number} [seq] - The load this belongs to; see `loadSeq`.
   */
  async function loadAllTracks(append = false, seq = loadSeq) {
    if (!append) {
        allTracksOffset = 0;
        allTracksHasMore = true;
        seenKeys = new SvelteMap();
    }
    const pageSize = append ? 100 : 25;
    const durationFilter = $viewMode === 'sets' ? { minDuration: 10 } : { maxDuration: 10 };
    
    let currentBatch = [];
    try {
      while (currentBatch.length < pageSize && allTracksHasMore) {
        const data = await subsonicJson('getSpotifyTracks', {
          artistId,
          offset: allTracksOffset,
          count: pageSize,
          sort: 'recent',
          deduplicate: $deduplicateEnabled ? 'true' : undefined,
          ...durationFilter
        });
        if (seq !== loadSeq) return;
        const tracksNode = data['subsonic-response']?.tracks;
        const newTracks = listOf(data, 'tracks.track');

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
      if (seq !== loadSeq) return;
      console.error(e);
      allTracksHasMore = false;
    }
  }

  /**
   * Loads additional artist information, such as similar artists. Every field is written on
   * every answer -- empty when this artist has none -- so a field the previous artist had can
   * never stay on screen for this one.
   *
   * @param {number} [seq] - The load this belongs to; see `loadSeq`.
   */
  async function loadArtistInfo(seq = loadSeq) {
    try {
      const data = await subsonicJson('getArtistInfo2', { id: artistId });
      if (seq !== loadSeq) return;
      const info = data['subsonic-response']?.artistInfo || data['subsonic-response']?.artistInfo2 || {};
      similarArtists = info.similarArtist
        ? (Array.isArray(info.similarArtist) ? info.similarArtist : [info.similarArtist])
        : [];
      biography = info.biography || "";
      mbid = info.musicBrainzId || "";
    } catch (e) {
      if (seq !== loadSeq) return;
      console.error(e);
    }
  }

  /**
   * Loads the genre rules MuMa holds for this artist.
   *
   * Keyed by name, not by `artistId`: that id comes from LMS and has nothing to do
   * with `library_artists.id`, which is why the previous version of this call
   * (`/api/artists/{artistId}`) hit a route that does not exist and left the chips
   * empty for as long as they have been on the page.
   *
   * @param {number} [seq] - The load this belongs to; see `loadSeq`.
   */
  async function loadArtistMuma(seq = loadSeq) {
    if (!artist?.name) return;
    try {
      const response = await fetch(
        `${$mumaApiUrl}/api/curation/artists/${encodeURIComponent(artist.name)}`,
        { headers: getHeaders() });
      if (seq !== loadSeq) return;
      if (response.ok) {
        const data = await response.json();
        if (data && data.genre_rules) {
          artist.genres = data.genre_rules.map((rule) => ({ name: rule.name }));
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
  <div class="p-8">{$t('common.loading')}</div>
{:else if !artist || loadFailed}
  <div class="p-8 text-[#b3b3b3]" role="alert">{$t('library.loadFailed')}</div>
{:else}
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
            {$t('artist.verified')}
         </div>
         <div class="flex items-center gap-3 justify-center md:justify-start">
           <h1 class="text-4xl md:text-7xl lg:text-9xl font-black m-0 leading-tight md:leading-none">{artist.name}</h1>
           {#if hasPermission('rules.manage')}
             <button
               class="bg-transparent border-none text-[#b3b3b3] hover:text-white transition-all hover:scale-110 cursor-pointer p-1 shrink-0"
               onclick={() => onnavigate?.(`artist-edit:${artistId}`)}
               title="Artiest bewerken"
               aria-label="Artiest bewerken"
             >
               <Pencil size={24} />
             </button>
           {/if}
         </div>
         <div class="flex flex-wrap items-center justify-center md:justify-start gap-4 mt-6">
           <button 
             class="w-12 h-12 md:w-14 md:h-14 bg-brand rounded-full flex items-center justify-center hover:scale-105 transition-transform shadow-lg border-none cursor-pointer"
             onclick={() => {
                if (allTracks.length > 0) {
                  currentTrack.set(allTracks[0]);
                  startQueue(allTracks, { name: artist.name });
                  playerState.update(s => ({ ...s, playing: true }));
                }
             }}
             aria-label={$t('common.play')}
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
                  startQueue(shuffled, { name: artist.name });
                  playerState.update(s => ({ ...s, playing: true, shuffle: true }));
                }
             }}
             title={$t('common.shufflePlay')}
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
             {#each (Array.isArray(artist.genres) ? artist.genres : [artist.genres]) as genre (genre.name)}
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
                <h2 class="text-2xl font-bold mb-4">{$t('artist.about', { name: artist.name })}</h2>
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
                                {$t('album.viewOnMusicBrainz')}
                            </a>
                        {/if}
                    </div>
                    <div class="absolute inset-0 bg-linear-to-t from-black/20 to-transparent pointer-events-none"></div>
                </div>
            </section>
        {/if}

        <section>
            <h2 class="text-2xl font-bold mb-4">{$viewMode === 'sets' ? $t('artist.allSets') : $t('artist.allTracks')}</h2>
            {#if allTracks.length > 0}
                <TrackList tracks={allTracks} onnavigate={onnavigate} />
                {#if allTracksHasMore}
                    <div class="flex justify-center py-4">
                        <button class="bg-transparent border border-[#727272] text-white px-8 py-2 rounded-[24px] font-bold cursor-pointer transition-all hover:border-white hover:scale-[1.04]" onclick={() => loadAllTracks(true)}>{$t('common.loadMore')}</button>
                    </div>
                {/if}
            {:else}
                <div class="text-[#b3b3b3] p-12 text-center border border-white/5 rounded-xl bg-white/5">
                    <p class="text-xl font-bold mb-2 text-white">{$viewMode === 'sets' ? $t('artist.noSets') : $t('artist.noTracks')}</p>
                    <p class="text-sm opacity-60">{$viewMode === 'sets' ? $t('artist.noSetsHelp') : $t('artist.noTracksHelp')}</p>
                </div>
            {/if}
        </section>

        {#each Object.entries(albumGroups).sort() as [type, groupAlbums] (type)}
            <section>
                <h2 class="text-2xl font-bold mb-4">{type}s</h2>
                <div class="grid grid-cols-3 gap-3 md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] md:gap-6">
                    {#each groupAlbums as album (album.id)}
                        <div
                          role="button"
                          tabindex="0"
                          class="bg-[#181818] p-2 md:p-4 rounded-lg transition-colors cursor-pointer hover:bg-[#282828]"
                          onclick={() => openAlbum(album.id)}
                          onkeydown={(e) => e.key === 'Enter' && openAlbum(album.id)}
                        >
                            <img
                              src={album.coverArt ? restUrl(`/rest/getCoverArt?id=${album.coverArt}&size=300&${$authParams}`) : '/images/spotify-fallback.svg'}
                              alt={album.name}
                              class="w-full aspect-square object-cover mb-2 md:mb-4 rounded shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
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
                <h2 class="text-2xl font-bold mb-4">{$t('artist.appearsOn')}</h2>
                <div class="grid grid-cols-3 gap-3 md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] md:gap-6">
                    {#each appearsOn as album (album.id)}
                        <div
                          role="button"
                          tabindex="0"
                          class="bg-[#181818] p-2 md:p-4 rounded-lg transition-colors cursor-pointer hover:bg-[#282828]"
                          onclick={() => openAlbum(album.id)}
                          onkeydown={(e) => e.key === 'Enter' && openAlbum(album.id)}
                        >
                            <img
                              src={album.coverArt ? restUrl(`/rest/getCoverArt?id=${album.coverArt}&size=300&${$authParams}`) : '/images/spotify-fallback.svg'}
                              alt={album.name}
                              class="w-full aspect-square object-cover mb-2 md:mb-4 rounded shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
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
                <h2 class="text-2xl font-bold mb-4">{$t('artist.similar')}</h2>
                <div class="grid grid-cols-3 gap-3 md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] md:gap-6">
                    {#each similarArtists as similar (similar.id)}
                        <div
                          role="button"
                          tabindex="0"
                          class="bg-[#181818] p-2 md:p-4 rounded-lg transition-colors cursor-pointer hover:bg-[#282828]"
                          onclick={() => openArtist(similar.id)}
                          onkeydown={(e) => e.key === 'Enter' && openArtist(similar.id)}
                        >
                            <div class="mb-2 md:mb-4">
                                <img
                                  src={getArtistImageUrl(similar, $authParams)}
                                  alt={similar.name}
                                  class="w-full aspect-square object-cover rounded-full shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
                                  onerror={(e) => e.target.src = '/images/unknown-artist.svg'}
                                />
                            </div>
                            <span class="block font-bold mb-1 whitespace-nowrap overflow-hidden text-ellipsis">{similar.name}</span>
                            <span class="text-sm text-[#b3b3b3]">{$t('common.artist')}</span>
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
