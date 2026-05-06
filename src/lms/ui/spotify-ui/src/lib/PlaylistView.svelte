<script>
  import { currentPlaylist, currentTrack, isPlaying, authParams, activeView } from './store.js';

  let tracks = [];
  const apiBase = '/rest';

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

  $: if ($currentPlaylist && $authParams) {
    fetchTracks($currentPlaylist.id);
  }

  function playTrack(track) {
    currentTrack.set(track);
    isPlaying.set(true);
  }
</script>

{#if $currentPlaylist}
  <div class="flex flex-col">
    <header class="flex items-end gap-6 mb-8">
      <div class="w-52 h-52 bg-[#282828] shadow-2xl flex items-center justify-center flex-shrink-0 overflow-hidden">
        {#if $currentPlaylist.coverArt}
          <img 
            src="/rest/getCoverArt?id={$currentPlaylist.coverArt}&{$authParams}&size=300" 
            alt="" 
            class="w-full h-full object-cover" 
            on:error={(e) => e.target.src = '/images/spotify-fallback.svg'}
          />
        {:else}
          <img src="/images/spotify-fallback.svg" alt="" class="w-24 h-24 opacity-20" />
        {/if}
      </div>
      <div>
        <div class="text-xs font-bold uppercase">Playlist</div>
        <h1 class="text-5xl md:text-7xl font-bold mb-4">{$currentPlaylist.name}</h1>
        <div class="text-[#b3b3b3] text-sm">{$currentPlaylist.comment || ''}</div>
      </div>
    </header>

    <div class="bg-black/20 -mx-8 px-8 py-6">
       <div class="flex items-center gap-8 mb-8">
         <button class="bg-spotify-green text-black w-14 h-14 rounded-full flex items-center justify-center shadow-xl hover:scale-105 transition cursor-pointer">
           <span class="text-2xl ml-1">▶</span>
         </button>
         <button class="text-[#b3b3b3] hover:text-white text-3xl transition cursor-pointer bg-transparent border-none">❤</button>
         <button class="text-[#b3b3b3] hover:text-white text-3xl transition cursor-pointer bg-transparent border-none">···</button>
       </div>

       <table class="w-full text-left text-[#b3b3b3] text-sm border-collapse">
         <thead>
           <tr class="border-b border-[#282828]/50 uppercase text-xs tracking-widest">
             <th class="pb-3 w-10 pl-4">#</th>
             <th class="pb-3">Titel</th>
             <th class="pb-3">Album</th>
             <th class="pb-3 text-right pr-4">Duur</th>
           </tr>
         </thead>
         <tbody class="before:block before:h-4">
           {#each tracks as track, i (track.id)}
             <tr 
               role="button"
               tabindex="0"
               on:dblclick={() => playTrack(track)}
               on:keydown={(e) => e.key === 'Enter' && playTrack(track)}
               class="hover:bg-[#282828]/50 group transition cursor-pointer rounded-md h-14"
             >
               <td class="w-10 pl-4">
                 <span class="group-hover:hidden">{i + 1}</span>
                 <span class="hidden group-hover:inline text-white">▶</span>
               </td>
               <td>
                <div class="flex items-center gap-3">
                  <div class="w-10 h-10 bg-[#282828] flex-shrink-0 overflow-hidden rounded">
                     <img 
                       src={track.coverArt ? `/rest/getCoverArt?id=${track.coverArt}&${$authParams}&size=40` : '/images/spotify-fallback.svg'} 
                       alt="" 
                       class="w-full h-full object-cover" 
                       on:error={(e) => e.target.src = '/images/spotify-fallback.svg'}
                     />
                  </div>
                  <div class="flex flex-col">
                     <div class="text-white font-medium truncate max-w-xs">{track.title}</div>
                     <div 
                        role="link"
                        tabindex="0"
                        class="hover:underline text-xs text-[#b3b3b3]" 
                        on:click|stopPropagation={() => activeView.set(`artist:${track.artistId}`)}
                        on:keydown|stopPropagation={(e) => e.key === 'Enter' && activeView.set(`artist:${track.artistId}`)}
                      >{track.artist}</div>
                   </div>
                 </div>
               </td>
               <td class="truncate max-w-xs">
                <span 
                  role="link"
                  tabindex="0"
                  class="hover:underline hover:text-white" 
                  on:click|stopPropagation={() => activeView.set(`album:${track.albumId}`)}
                  on:keydown|stopPropagation={(e) => e.key === 'Enter' && activeView.set(`album:${track.albumId}`)}
                >{track.album}</span>
              </td>
               <td class="text-right pr-4 font-mono">
                 {Math.floor(track.duration / 60)}:{(track.duration % 60).toString().padStart(2, '0')}
               </td>
             </tr>
           {/each}
         </tbody>
       </table>
    </div>
  </div>
{/if}
