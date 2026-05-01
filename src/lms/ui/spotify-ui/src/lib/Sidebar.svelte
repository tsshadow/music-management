<script>
  import { curatedPlaylists, currentPlaylist, view } from './store.js';
</script>

<aside class="w-64 bg-black flex flex-col flex-shrink-0 p-6 space-y-6">
  <div class="text-white font-bold text-2xl mb-4 flex items-center gap-2">
    <span class="text-spotify-green">LMS</span> Spotify
  </div>

  <nav class="space-y-4">
    <button on:click={() => view.set('home')} class="flex items-center gap-4 text-spotify-text hover:text-white transition w-full text-left">
      <div class="w-6 h-6 bg-spotify-text rounded-sm"></div> <span class="font-bold">Home</span>
    </button>
    <button on:click={() => view.set('search')} class="flex items-center gap-4 text-spotify-text hover:text-white transition w-full text-left">
      <div class="w-6 h-6 bg-spotify-text rounded-sm"></div> <span class="font-bold">Search</span>
    </button>
    <button class="flex items-center gap-4 text-spotify-text hover:text-white transition w-full text-left">
      <div class="w-6 h-6 bg-spotify-text rounded-sm"></div> <span class="font-bold">Your Library</span>
    </button>
  </nav>

  <div class="pt-6 space-y-4 border-t border-spotify-light">
    <button class="flex items-center gap-4 text-spotify-text hover:text-white transition w-full text-left">
      <div class="w-6 h-6 bg-spotify-text rounded-sm text-black flex items-center justify-center font-bold">+</div> <span class="font-bold">Create Playlist</span>
    </button>
    <button class="flex items-center gap-4 text-spotify-text hover:text-white transition w-full text-left">
      <div class="bg-gradient-to-br from-indigo-700 to-blue-300 w-6 h-6 rounded-sm flex items-center justify-center">
        ❤
      </div>
      <span class="font-bold">Liked Songs</span>
    </button>
  </div>

  <div class="flex-1 overflow-y-auto space-y-2 pt-4 scrollbar-hide">
    {#each $curatedPlaylists as playlist}
      <button 
        on:click={() => { currentPlaylist.set(playlist); view.set('playlist'); }}
        class="block text-spotify-text hover:text-white transition truncate text-sm w-full text-left"
      >
        {playlist.name}
      </button>
    {/each}
  </div>
</aside>
