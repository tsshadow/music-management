<script>
  import { currentTrack, playerState, authParams, playlist, isMobile, highlightedTrackId } from './store.js';
  import ArtistList from './ArtistList.svelte';

  const { tracks = [], isQueue = false, playlistId = null, onremove = null, onnavigate } = $props();

  /**
   * Updates the rating of a track.
   *
   * @param {Object} track - The track object.
   * @param {number} rating - The new rating (1-5).
   */
  async function updateRating(track, rating) {
    const newRating = track.userRating === rating ? 0 : rating;
    const oldRating = track.userRating;

    // Optimistic update
    track.userRating = newRating;

    try {
      const response = await fetch(`/rest/setRating?id=${track.id}&rating=${newRating}&${$authParams}`);
      if (!response.ok) throw new Error('Failed to update rating');
    } catch (e) {
      console.error("Failed to update rating:", e);
      track.userRating = oldRating;
    }
  }

  /**
   * Sets the current track and starts playback.
   * If not in queue mode, also updates the global playlist.
   *
   * @param {Object} track - The track object to play.
   */
  function playTrack(track) {
    currentTrack.set(track);
    if (!isQueue) {
        playlist.set(tracks);
    }
    playerState.update(s => ({ ...s, playing: true }));
  }

  /**
   * Removes a track from the playlist by its index.
   *
   * @param {Event} e - The click event.
   * @param {number} index - The index of the track in the playlist.
   */
  function removeTrack(e, index) {
      e.stopPropagation();
      if (isQueue) {
          playlist.update(p => {
              const newP = [...p];
              newP.splice(index, 1);
              return newP;
          });
      }
      if (onremove) {
          onremove(index);
      }
  }

  /**
   * Moves a track up or down in the playlist.
   *
   * @param {Event} e - The click event.
   * @param {number} index - The current index of the track.
   * @param {number} direction - The direction to move (-1 for up, 1 for down).
   */
  function moveTrack(e, index, direction) {
      e.stopPropagation();
      playlist.update(p => {
          const newP = [...p];
          const newIndex = index + direction;
          if (newIndex < 0 || newIndex >= newP.length) return newP;
          [newP[index], newP[newIndex]] = [newP[newIndex], newP[index]];
          return newP;
      });
  }

  /**
   * Adds a track to the playlist immediately after the current track.
   *
   * @param {Event} e - The click event.
   * @param {Object} track - The track to add.
   */
  function addAfterCurrent(e, track) {
      e.stopPropagation();
      playlist.update(p => {
          const newP = [...p];
          const currentIndex = newP.findIndex(t => String(t.id) === String($currentTrack?.id));
          if (currentIndex === -1) {
              newP.push({ ...track });
          } else {
              newP.splice(currentIndex + 1, 0, { ...track });
          }
          return newP;
      });
  }

  /**
   * Adds a track to the end of the current playlist.
   *
   * @param {Event} e - The click event.
   * @param {Object} track - The track to add.
   */
  function addToEnd(e, track) {
      e.stopPropagation();
      playlist.update(p => [...p, { ...track }]);
  }

  /**
   * Formats milliseconds into a "M:SS" string.
   *
   * @param {number} ms - Time in milliseconds.
   * @returns {string} Formatted time string.
   */
  function formatTime(ms) {
    if (!ms) return "0:00";
    const minutes = Math.floor(ms / 60000);
    const seconds = ((ms % 60000) / 1000).toFixed(0);
    return minutes + ":" + (seconds < 10 ? '0' : '') + seconds;
  }

  /**
   * Formats an ISO date string (YYYY-MM-DD) into DD-MM-YYYY.
   *
   * @param {string} dateStr - The date string from the backend.
   * @returns {string|null} Formatted date or null if invalid.
   */
  function formatDate(dateStr) {
    if (!dateStr) return null;
    const parts = dateStr.split('T')[0].split('-');
    if (parts.length === 3) {
      // YYYY-MM-DD -> DD-MM-YYYY
      return `${parts[2]}-${parts[1]}-${parts[0]}`;
    }
    return null;
  }

  $effect(() => {
    if ($highlightedTrackId) {
      // Use a small timeout to ensure the DOM is updated if tracks just loaded
      setTimeout(() => {
        const element = document.querySelector(`[data-track-id="${$highlightedTrackId}"]`);
        if (element) {
          element.scrollIntoView({ behavior: 'smooth', block: 'center' });
          // Clear highlight after 3 seconds
          setTimeout(() => highlightedTrackId.set(null), 3000);
        }
      }, 100);
    }
  });
</script>

<table class="w-full border-collapse text-[#b3b3b3] text-sm">
  <thead class="border-b border-white/10">
    <tr>
      <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em] w-[50px] text-right hidden md:table-cell">#</th>
      <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em]">Titel</th>
      {#if !isQueue}
        <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em] hidden md:table-cell">Album</th>
        <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em] hidden md:table-cell">Genre</th>
        <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em] w-20 hidden md:table-cell">Datum</th>
        <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em] w-32 hidden lg:table-cell text-center">Rating</th>
      {/if}
      <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em] w-[80px] md:w-[100px] text-right">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" class="inline">
          <path d="M8 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM0 8a8 8 0 1116 0A8 8 0 010 8z"></path>
          <path d="M8 4a.5.5 0 01.5.5v3h3a.5.5 0 010 1H8a.5.5 0 01-.5-.5v-4A.5.5 0 018 4z"></path>
        </svg>
      </th>
      <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em] w-[100px] text-center"></th>
    </tr>
  </thead>
  <tbody>
    {#each tracks as track, i (track.id + '-' + i)}
      <tr
        role="button"
        tabindex="0"
        data-track-id={track.id}
        class="group hover:bg-white/10 active:bg-white/5 hover:text-white h-14 md:h-16 cursor-pointer select-none {String($currentTrack?.id) === String(track.id) ? 'text-brand' : ''} {String($highlightedTrackId) === String(track.id) ? 'bg-brand/20 text-white' : ''}"
        onclick={() => { if ($isMobile) playTrack(track); }}
        ondblclick={() => { if (!$isMobile) playTrack(track); }}
        onkeydown={(e) => e.key === 'Enter' && playTrack(track)}
      >
        <td class="p-2 px-4 text-right relative hidden md:table-cell">
            <span class="block group-hover:hidden">{i + 1}</span>
            <button
              aria-label="Afspelen"
              class="hidden group-hover:block bg-transparent border-none text-white cursor-pointer p-0 absolute right-4 top-1/2 -translate-y-1/2"
              onclick={() => playTrack(track)}
            >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                    <path d="M7 6v12l10-6z"></path>
                </svg>
            </button>
        </td>
        <td class="p-2 px-4">
          <div class="flex items-center gap-3">
            <img
              src={track.coverArt ? `/rest/getCoverArt?id=${track.coverArt}&size=48&${$authParams}` : '/images/spotify-fallback.svg'}
              alt=""
              class="w-10 h-10 md:w-12 md:h-12 rounded shadow"
              onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
            />
            <div class="flex flex-col min-w-0">
              <span class="text-sm md:text-base font-medium truncate {String($currentTrack?.id) === String(track.id) ? 'text-brand' : 'text-white'}">{track.title}</span>
              <ArtistList
                artist={track.artist}
                artistId={track.artistId}
                artists={track.artists}
                active={String($currentTrack?.id) === String(track.id)}
                onnavigate={onnavigate}
              />
            </div>
          </div>
        </td>
        {#if !isQueue}
          <td class="p-2 px-4 hidden md:table-cell">
            <span
              role="link"
              tabindex="0"
              class="hover:underline cursor-pointer"
              onclick={() => onnavigate && onnavigate(`album:${track.albumId}`)}
              onkeydown={(e) => e.key === 'Enter' && onnavigate && onnavigate(`album:${track.albumId}`)}
            >{track.album || ''}</span>
          </td>
          <td class="p-2 px-4 text-xs italic opacity-80 max-w-[150px] truncate hidden md:table-cell" title={track.genre || ''}>
            {#if track.genre}
              <span
                role="link"
                tabindex="0"
                class="hover:underline cursor-pointer"
                onclick={(e) => { e.stopPropagation(); onnavigate && onnavigate(`genre:${track.genre}`); }}
                onkeydown={(e) => { if (e.key === 'Enter') { e.stopPropagation(); onnavigate && onnavigate(`genre:${track.genre}`); } }}
              >{track.genre}</span>
            {/if}
          </td>
          <td class="p-2 px-4 hidden md:table-cell">{formatDate(track.date) || track.year || ''}</td>
          <td class="p-2 px-4 hidden lg:table-cell">
            <div class="flex gap-0.5 justify-center">
              {#each [1, 2, 3, 4, 5] as star}
                <button
                  aria-label="{star} sterren"
                  class="bg-transparent border-none p-0.5 cursor-pointer transition-colors { (track.userRating || 0) >= star ? 'text-brand' : 'text-white/10 hover:text-white/30' }"
                  onclick={(e) => { e.stopPropagation(); updateRating(track, star); }}
                >
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                    <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"></path>
                  </svg>
                </button>
              {/each}
            </div>
          </td>
        {/if}
        <td class="p-2 px-4 text-right text-xs md:text-sm">{formatTime(track.duration * 1000)}</td>
        <td class="p-2 px-4 text-center">
          <div class="flex gap-1 justify-center opacity-0 group-hover:opacity-100 transition-opacity">
              {#if isQueue}
                      <button
                        aria-label="Omhoog"
                        title="Omhoog"
                        class="bg-transparent border-none text-[#b3b3b3] cursor-pointer p-1 flex items-center justify-center rounded hover:bg-[#333] hover:text-white disabled:text-[#555] disabled:cursor-not-allowed"
                        onclick={(e) => moveTrack(e, i, -1)}
                        disabled={i === 0}
                      >
                          <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                              <path d="M7 14l5-5 5 5z"></path>
                          </svg>
                      </button>
                      <button
                        aria-label="Omlaag"
                        title="Omlaag"
                        class="bg-transparent border-none text-[#b3b3b3] cursor-pointer p-1 flex items-center justify-center rounded hover:bg-[#333] hover:text-white disabled:text-[#555] disabled:cursor-not-allowed"
                        onclick={(e) => moveTrack(e, i, 1)}
                        disabled={i === tracks.length - 1}
                      >
                          <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                              <path d="M7 10l5 5 5-5z"></path>
                          </svg>
                      </button>
              {/if}

              {#if isQueue || playlistId}
                  <button
                    aria-label="Verwijderen"
                    title="Verwijderen"
                    class="bg-transparent border-none text-[#b3b3b3] cursor-pointer p-1 flex items-center justify-center rounded hover:bg-[#333] hover:text-white hover:text-pink-500"
                    onclick={(e) => removeTrack(e, i)}
                  >
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                          <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"></path>
                      </svg>
                  </button>
              {/if}

              {#if !isQueue}
                  <button
                    aria-label="Hierna afspelen"
                    title="Hierna afspelen"
                    class="bg-transparent border-none text-[#b3b3b3] cursor-pointer p-1 flex items-center justify-center rounded hover:bg-[#333] hover:text-white"
                    onclick={(e) => addAfterCurrent(e, track)}
                  >
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                          <path d="M13 13h5v2h-5v5h-2v-5H6v-2h5V8h2v5z"></path>
                          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"></path>
                      </svg>
                  </button>
                  <button
                    aria-label="Aan wachtrij toevoegen"
                    title="Aan wachtrij toevoegen"
                    class="bg-transparent border-none text-[#b3b3b3] cursor-pointer p-1 flex items-center justify-center rounded hover:bg-[#333] hover:text-white"
                    onclick={(e) => addToEnd(e, track)}
                  >
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                          <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"></path>
                      </svg>
                  </button>
              {/if}
          </div>
        </td>
      </tr>
    {/each}
  </tbody>
</table>

<style>
</style>
