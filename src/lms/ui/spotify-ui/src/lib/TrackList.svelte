<script>
  import { currentTrack, playerState, authParams, playlist } from './store.js';
  import ArtistList from './ArtistList.svelte';

  const { tracks = [], isQueue = false, onnavigate } = $props();

  function playTrack(track, index) {
    currentTrack.set(track);
    if (!isQueue) {
        playlist.set(tracks);
    }
    playerState.update(s => ({ ...s, playing: true }));
  }

  function removeTrack(e, index) {
      e.stopPropagation();
      playlist.update(p => {
          const newP = [...p];
          newP.splice(index, 1);
          return newP;
      });
  }

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

  function formatTime(ms) {
    if (!ms) return "0:00";
    const minutes = Math.floor(ms / 60000);
    const seconds = ((ms % 60000) / 1000).toFixed(0);
    return minutes + ":" + (seconds < 10 ? '0' : '') + seconds;
  }
</script>

<table class="w-full border-collapse text-[#b3b3b3] text-sm">
  <thead class="border-b border-white/10">
    <tr>
      <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em] w-[50px] text-right">#</th>
      <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em]">Titel</th>
      {#if !isQueue}
        <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em]">Album</th>
        <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em]">Genre</th>
        <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em] w-20">Datum</th>
      {/if}
      <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em] w-[100px] text-right">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" class="inline">
          <path d="M8 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM0 8a8 8 0 1116 0A8 8 0 010 8z"></path>
          <path d="M8 4a.5.5 0 01.5.5v3h3a.5.5 0 010 1H8a.5.5 0 01-.5-.5v-4A.5.5 0 018 4z"></path>
        </svg>
      </th>
      {#if isQueue}
        <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em] w-[100px] text-center"></th>
      {/if}
    </tr>
  </thead>
  <tbody>
    {#each tracks as track, i (track.id || i)}
      <tr 
        role="button"
        tabindex="0"
        class="group hover:bg-white/10 hover:text-white h-14 {$currentTrack?.id === track.id ? 'text-spotify-green' : ''}" 
        ondblclick={() => playTrack(track)}
        onkeydown={(e) => e.key === 'Enter' && playTrack(track)}
      >
        <td class="p-2 px-4 text-right relative">
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
              src={track.coverArt ? `/rest/getCoverArt?id=${track.coverArt}&size=40&${$authParams}` : '/images/spotify-fallback.svg'} 
              alt="" 
              class="w-10 h-10 rounded"
              onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
            />
            <div class="flex flex-col">
              <span class="text-base font-medium {$currentTrack?.id === track.id ? 'text-spotify-green' : 'text-white'}">{track.title}</span>
              <ArtistList 
                artist={track.artist} 
                artistId={track.artistId} 
                artists={track.artists} 
                active={$currentTrack?.id === track.id}
                onnavigate={onnavigate} 
              />
            </div>
          </div>
        </td>
        {#if !isQueue}
          <td class="p-2 px-4">
            <span 
              role="link"
              tabindex="0"
              class="hover:underline cursor-pointer" 
              onclick={() => onnavigate && onnavigate(`album:${track.albumId}`)}
              onkeydown={(e) => e.key === 'Enter' && onnavigate && onnavigate(`album:${track.albumId}`)}
            >{track.album || ''}</span>
          </td>
          <td class="p-2 px-4 text-xs italic opacity-80 max-w-[150px] truncate" title={track.genre || ''}>{track.genre || ''}</td>
          <td class="p-2 px-4">{track.year || ''}</td>
        {/if}
        <td class="p-2 px-4 text-right">{formatTime(track.duration * 1000)}</td>
        {#if isQueue}
          <td class="p-2 px-4 text-center">
            <div class="flex gap-1 justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                <button 
                  aria-label="Omhoog"
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
                  class="bg-transparent border-none text-[#b3b3b3] cursor-pointer p-1 flex items-center justify-center rounded hover:bg-[#333] hover:text-white disabled:text-[#555] disabled:cursor-not-allowed" 
                  onclick={(e) => moveTrack(e, i, 1)} 
                  disabled={i === tracks.length - 1}
                >
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                        <path d="M7 10l5 5 5-5z"></path>
                    </svg>
                </button>
                <button 
                  aria-label="Verwijderen"
                  class="bg-transparent border-none text-[#b3b3b3] cursor-pointer p-1 flex items-center justify-center rounded hover:bg-[#333] hover:text-white hover:text-pink-500" 
                  onclick={(e) => removeTrack(e, i)}
                >
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                        <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"></path>
                    </svg>
                </button>
            </div>
          </td>
        {/if}
      </tr>
    {/each}
  </tbody>
</table>

<style>
</style>
