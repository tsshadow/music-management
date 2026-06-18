<script>
  import { untrack } from 'svelte';
  import { currentPlaylist, authParams, playlist, currentTrack, playerState } from './store.js';
  import TrackList from './TrackList.svelte';

  const { onnavigate } = $props();
  let tracks = $state([]);
  const apiBase = '/rest';

  /**
   * Fetches the tracks for a specific playlist.
   * 
   * @param {string} id - The Subsonic playlist ID.
   */
  async function fetchTracks(id) {
    if (!id || !$authParams) return;
    try {
      const resp = await fetch(`${apiBase}/getPlaylist?id=${encodeURIComponent(id)}&${$authParams}`);
      const data = await resp.json();
      const playlistData = data['subsonic-response']?.playlist;
      const result = playlistData?.entry || [];
      tracks = Array.isArray(result) ? result : [result];

      if (playlistData && (!$currentPlaylist.name || $currentPlaylist.id !== playlistData.id)) {
        currentPlaylist.set(playlistData);
      }
    } catch (e) {
      console.error("Failed to fetch tracks", e);
    }
  }

  $effect(() => {
    const id = $currentPlaylist?.id;
    const auth = $authParams;
    if (id && auth) {
      untrack(() => fetchTracks(id));
    }
  });
  /**
   * Loads all tracks of the current playlist into the global queue and starts playback.
   */
  function playAll() {
    if (tracks.length > 0) {
      playlist.set(tracks);
      currentTrack.set(tracks[0]);
      playerState.update(s => ({ ...s, playing: true }));
    }
  }
</script>

{#if $currentPlaylist}
  <div class="flex flex-col">
    <header class="flex flex-col md:flex-row items-center md:items-end gap-6 mb-8 text-center md:text-left">
      <div class="w-40 h-40 md:w-52 md:h-52 bg-[#282828] shadow-2xl flex items-center justify-center flex-shrink-0 overflow-hidden">
        {#if $currentPlaylist.coverArt}
          <img 
            src="/rest/getCoverArt?id={$currentPlaylist.coverArt}&{$authParams}&size=300" 
            alt="" 
            class="w-full h-full object-cover" 
            onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
          />
        {:else}
          <img src="/images/spotify-fallback.svg" alt="" class="w-20 h-20 md:w-24 md:h-24 opacity-20" />
        {/if}
      </div>
      <div>
        <div class="text-xs font-bold uppercase">Playlist</div>
        <h1 class="text-4xl md:text-7xl font-bold mb-4">{$currentPlaylist.name}</h1>
        <div class="text-[#b3b3b3] text-sm">{$currentPlaylist.comment || ''}</div>
      </div>
    </header>

    <div class="bg-black/20 -mx-8 px-8 py-6">
       <div class="flex items-center gap-8 mb-8">
         <button 
           class="bg-spotify-green text-black w-14 h-14 rounded-full flex items-center justify-center shadow-xl hover:scale-105 transition cursor-pointer"
           onclick={playAll}
         >
           <span class="text-2xl ml-1">▶</span>
         </button>
         <button class="text-[#b3b3b3] hover:text-white text-3xl transition cursor-pointer bg-transparent border-none">❤</button>
         <button class="text-[#b3b3b3] hover:text-white text-3xl transition cursor-pointer bg-transparent border-none">···</button>
       </div>

       <TrackList {tracks} onnavigate={onnavigate} />
    </div>
  </div>
{/if}
