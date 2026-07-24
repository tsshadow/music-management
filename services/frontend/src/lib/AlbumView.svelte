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
   * Toggles the starred status of the album.
   */
  async function toggleStar() {
    if (!album) return;
    const isCurrentlyStarred = !!album.starred;
    const endpoint = isCurrentlyStarred ? 'unstar' : 'star';
    
    // Optimistic update
    if (isCurrentlyStarred) delete album.starred;
    else album.starred = new Date().toISOString();

    try {
      const response = await fetch(`/rest/${endpoint}?albumId=${albumId}&${$authParams}`);
      if (!response.ok) throw new Error('Failed to toggle star');
    } catch (e) {
      console.error(e);
      // Rollback
      if (isCurrentlyStarred) album.starred = new Date().toISOString();
      else delete album.starred;
    }
  }

  /**
   * Filtered tracks based on viewMode (songs vs sets), grouped by disc.
   */
  const groupedTracks = $derived.by(() => {
    let filtered;
    if ($viewMode === 'sets') {
      filtered = allTracks.filter(t => t.duration >= 600);
    } else {
      filtered = allTracks.filter(t => t.duration < 600);
    }

    const groups = {};
    filtered.forEach(t => {
      const disc = t.discNumber || 1;
      if (!groups[disc]) groups[disc] = [];
      groups[disc].push(t);
    });

    return Object.entries(groups).sort(([a], [b]) => Number(a) - Number(b));
  });

  const hasMultipleDiscs = $derived(groupedTracks.length > 1);

  /**
   * Helper to get disc title if available.
   * @param {number} discNumber
   */
  function getDiscTitle(discNumber) {
    if (album && album.discTitles) {
      const titles = Array.isArray(album.discTitles) ? album.discTitles : [album.discTitles];
      const found = titles.find(t => Number(t.disc) === Number(discNumber));
      if (found) return found.title;
    }
    return `Disc ${discNumber}`;
  }

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
         <div class="flex flex-wrap items-center justify-center md:justify-start gap-4 my-4">
           <button 
             class="w-12 h-12 md:w-14 md:h-14 bg-brand rounded-full flex items-center justify-center hover:scale-105 transition-transform shadow-lg border-none cursor-pointer"
             onclick={() => {
                if (tracks.length > 0) {
                  currentTrack.set(tracks[0]);
                  playlist.set(tracks);
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
                if (tracks.length > 0) {
                  const shuffled = [...tracks].sort(() => Math.random() - 0.5);
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
             class="bg-transparent border-none p-0 cursor-pointer transition-transform hover:scale-110 {album.starred ? 'text-brand' : 'text-[#b3b3b3] hover:text-white'}"
             onclick={toggleStar}
             title={album.starred ? "Verwijderen uit favorieten" : "Toevoegen aan favorieten"}
           >
              {#if album.starred}
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
         <div class="flex flex-wrap items-center justify-center md:justify-start gap-1 font-bold">
            <ArtistList
              artist={album.artist}
              artistId={album.artistId}
              artists={album.albumArtists}
              onnavigate={onnavigate}
            />
            {#if album.year} <span class="text-[#b3b3b3] hidden md:inline">•</span> {album.year}{/if}
            {#if allTracks.length > 0} <span class="text-[#b3b3b3]">•</span> {allTracks.length} nummers{/if}
         </div>
       </div>
    </header>

    <div class="p-6 md:p-8 pt-0">
      {#if groupedTracks.length > 0}
        {#each groupedTracks as [disc, tracks]}
          <div class={hasMultipleDiscs ? "mt-8 first:mt-0" : ""}>
            {#if hasMultipleDiscs}
              <div class="flex items-center gap-4 mb-4 text-[#b3b3b3]">
                <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"></path>
                </svg>
                <h3 class="text-lg font-bold">{getDiscTitle(disc)}</h3>
              </div>
            {/if}
            <TrackList {tracks} onnavigate={onnavigate} />
          </div>
        {/each}
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

      {#if (albumInfo && albumInfo.notes) || (albumInfo && albumInfo.musicBrainzId)}
        <div class="mt-8 border-t border-[#282828] pt-8">
            <h3 class="text-xl font-bold mb-4">Over dit album</h3>
            {#if albumInfo.notes}
                <p class="text-[#b3b3b3] whitespace-pre-wrap mb-4">{albumInfo.notes}</p>
            {/if}
            {#if albumInfo.musicBrainzId}
                <a 
                    href="https://musicbrainz.org/release/{albumInfo.musicBrainzId}" 
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
      {/if}
    </div>
  </div>
{/if}

<style>
</style>
