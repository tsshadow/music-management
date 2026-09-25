<script>
  import { t } from './i18n/index.js';
  import { untrack } from 'svelte';
  import { currentPlaylist, authParams, currentTrack, playerState, restUrl } from './store.js';
  import { listOf, subsonicJson } from './subsonic.js';
  import TrackList from './TrackList.svelte';
  import { recordPlace } from './recentPlaces.js';
  import { startQueue } from './queue.js';

  const { onnavigate } = $props();
  let tracks = $state([]);

  /**
   * Fetches the tracks for a specific playlist.
   *
   * @param {string} id - The Subsonic playlist ID.
   */
  async function fetchTracks(id) {
    if (!id || !$authParams) return;
    try {
      const data = await subsonicJson('getPlaylist', { id });
      const playlistData = data['subsonic-response']?.playlist;
      tracks = listOf(data, 'playlist.entry');

      if (playlistData) {
        // Backfills the name for the 'playlist:<id>' place App's handleNavigate recorded bare.
        recordPlace(`playlist:${id}`, playlistData.name);
        if (!$currentPlaylist.name || $currentPlaylist.id !== playlistData.id) {
          currentPlaylist.set(playlistData);
        }
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
      // The queue names 'playlist:<id>', not 'playlist-detail': only the former is a place
      // the header can navigate back to (see App.svelte's handleNavigate).
      startQueue(tracks, { name: $currentPlaylist?.name, view: `playlist:${$currentPlaylist?.id}` });
      currentTrack.set(tracks[0]);
      playerState.update(s => ({ ...s, playing: true }));
    }
  }

  /**
   * Removes a track from the saved playlist.
   *
   * @param {number} index - The index of the track to remove.
   */
  async function handleRemove(index) {
    const id = $currentPlaylist?.id;
    if (!id || !$authParams) return;
    try {
      const resp = await fetch(restUrl(`/rest/updatePlaylist?playlistId=${encodeURIComponent(id)}&songIndexToRemove=${index}&${$authParams}`));
      if (resp.ok) {
        tracks = tracks.filter((_, i) => i !== index);
      }
    } catch (e) {
      console.error("Failed to remove track from playlist", e);
    }
  }
</script>

{#if $currentPlaylist}
  <div class="flex flex-col">
    <header class="flex flex-col md:flex-row items-center md:items-end gap-6 mb-8 text-center md:text-left">
      <div class="w-40 h-40 md:w-52 md:h-52 bg-muma-spotify-light shadow-2xl flex items-center justify-center flex-shrink-0 overflow-hidden">
        {#if $currentPlaylist.coverArt}
          <img
            src={restUrl(`/rest/getCoverArt?id=${$currentPlaylist.coverArt}&${$authParams}&size=300`)}
            alt=""
            class="w-full h-full object-cover"
            onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
          />
        {:else}
          <img src="/images/spotify-fallback.svg" alt="" class="w-20 h-20 md:w-24 md:h-24 opacity-20" />
        {/if}
      </div>
      <div>
        <div class="text-xs font-bold uppercase">{$t('common.playlist')}</div>
        <h1 class="text-4xl md:text-7xl font-bold mb-4">{$currentPlaylist.name}</h1>
        <div class="text-muma-spotify-text text-sm">{$currentPlaylist.comment || ''}</div>
      </div>
    </header>

    <div class="bg-black/20 -mx-8 px-8 py-6">
       <div class="flex items-center gap-8 mb-8">
         <button
           class="bg-brand text-black w-14 h-14 rounded-full flex items-center justify-center shadow-xl hover:scale-105 transition cursor-pointer"
           onclick={playAll}
         >
           <span class="text-2xl ml-1">▶</span>
         </button>
         <button class="text-muma-spotify-text hover:text-white text-3xl transition cursor-pointer bg-transparent border-none">❤</button>
         <button class="text-muma-spotify-text hover:text-white text-3xl transition cursor-pointer bg-transparent border-none">···</button>
       </div>

       <TrackList {tracks} playlistId={$currentPlaylist?.id} onremove={handleRemove} onnavigate={onnavigate} />
    </div>
  </div>
{/if}
