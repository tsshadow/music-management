<script>
  import { currentPlaylist, currentTrack, isPlaying } from './store.js';

  let tracks = [];
  let apiBase = '/rest';

  async function fetchTracks(id) {
    if (!id) return;
    try {
      const resp = await fetch(`${apiBase}/getPlaylist?id=${encodeURIComponent(id)}&u=admin&t=admin&s=salt&v=1.16.1&c=spotify-ui&f=json`);
      const data = await resp.json();
      tracks = data['subsonic-response'].playlist.entry || [];
    } catch (e) {
      console.error("Failed to fetch tracks", e);
    }
  }

  $: if ($currentPlaylist) {
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
      <div class="w-52 h-52 bg-spotify-light shadow-2xl flex items-center justify-center text-6xl flex-shrink-0">
        💿
      </div>
      <div>
        <div class="text-xs font-bold uppercase">Playlist</div>
        <h1 class="text-7xl font-bold mb-4">{$currentPlaylist.name}</h1>
        <div class="text-spotify-text text-sm">{$currentPlaylist.comment}</div>
      </div>
    </header>

    <div class="bg-black/20 -mx-8 px-8 py-6">
       <div class="flex items-center gap-8 mb-8">
         <button class="bg-spotify-green text-black w-14 h-14 rounded-full flex items-center justify-center shadow-xl hover:scale-105 transition">
           <span class="text-2xl ml-1">▶</span>
         </button>
         <button class="text-spotify-text hover:text-white text-3xl transition">❤</button>
         <button class="text-spotify-text hover:text-white text-3xl transition">···</button>
       </div>

       <table class="w-full text-left text-spotify-text text-sm border-collapse">
         <thead>
           <tr class="border-b border-spotify-light/20 uppercase text-xs tracking-widest">
             <th class="pb-3 w-10 pl-4">#</th>
             <th class="pb-3">Titel</th>
             <th class="pb-3">Album</th>
             <th class="pb-3 text-right pr-4">Duur</th>
           </tr>
         </thead>
         <tbody class="before:block before:h-4">
           {#each tracks as track, i}
             <tr 
               on:dblclick={() => playTrack(track)}
               class="hover:bg-spotify-light/20 group transition cursor-pointer rounded-md"
             >
               <td class="py-2 w-10 pl-4">
                 <span class="group-hover:hidden">{i + 1}</span>
                 <span class="hidden group-hover:inline text-white">▶</span>
               </td>
               <td class="py-2">
                 <div class="flex items-center gap-3">
                   <div class="w-10 h-10 bg-spotify-light flex-shrink-0">
                      <img src="/rest/getCoverArt?id={track.coverArt}&u=admin&t=admin&s=salt&v=1.16.1&c=spotify-ui&size=40" alt="" class="w-full h-full" />
                   </div>
                   <div>
                     <div class="text-white font-medium truncate max-w-xs">{track.title}</div>
                     <div class="hover:underline text-xs text-spotify-text">{track.artist}</div>
                   </div>
                 </div>
               </td>
               <td class="py-2 truncate max-w-xs">
                 <span class="hover:underline hover:text-white">{track.album}</span>
               </td>
               <td class="py-2 text-right pr-4 font-mono">
                 {Math.floor(track.duration / 60)}:{(track.duration % 60).toString().padStart(2, '0')}
               </td>
             </tr>
           {/each}
         </tbody>
       </table>
    </div>
  </div>
{/if}
