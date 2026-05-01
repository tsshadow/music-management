<script>
  import { view, curatedPlaylists, currentPlaylist } from './store.js';
  import PlaylistView from './PlaylistView.svelte';

  function getGreeting() {
    const hour = new Date().getHours();
    if (hour < 12) return "Goedemorgen";
    if (hour < 18) return "Goedemiddag";
    return "Goedenavond";
  }
</script>

<div class="p-8">
  {#if $view === 'home'}
    <header class="flex justify-between items-center mb-8">
      <h1 class="text-3xl font-bold">{getGreeting()}</h1>
    </header>

    <section>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
        {#each $curatedPlaylists.slice(0, 6) as playlist}
          <button 
            on:click={() => { currentPlaylist.set(playlist); view.set('playlist'); }}
            class="bg-spotify-light/40 hover:bg-spotify-light transition rounded-md flex items-center gap-4 overflow-hidden group shadow-lg"
          >
            <div class="w-20 h-20 bg-spotify-light flex-shrink-0 shadow-xl flex items-center justify-center">
               <span class="text-2xl">🎵</span>
            </div>
            <span class="font-bold truncate">{playlist.name}</span>
            <div class="ml-auto mr-4 opacity-0 group-hover:opacity-100 transition translate-y-2 group-hover:translate-y-0">
               <div class="bg-spotify-green text-black w-10 h-10 rounded-full flex items-center justify-center shadow-2xl">▶</div>
            </div>
          </button>
        {/each}
      </div>

      <h2 class="text-2xl font-bold mb-4 hover:underline cursor-pointer">Speciaal voor jou gecureerd</h2>
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6">
        {#each $curatedPlaylists as playlist}
          <div 
            on:click={() => { currentPlaylist.set(playlist); view.set('playlist'); }}
            class="bg-spotify-dark p-4 rounded-lg hover:bg-spotify-light/20 transition cursor-pointer group shadow-xl"
          >
            <div class="aspect-square bg-spotify-light rounded-md mb-4 shadow-lg relative overflow-hidden flex items-center justify-center">
                <span class="text-5xl">💿</span>
                <div class="absolute inset-0 bg-gradient-to-br from-spotify-green/20 to-black/20"></div>
                <div class="absolute bottom-2 right-2 opacity-0 group-hover:opacity-100 transition translate-y-2 group-hover:translate-y-0">
                   <div class="bg-spotify-green text-black w-12 h-12 rounded-full flex items-center justify-center shadow-2xl">▶</div>
                </div>
            </div>
            <div class="font-bold mb-1 truncate">{playlist.name}</div>
            <div class="text-spotify-text text-sm line-clamp-2">{playlist.comment}</div>
          </div>
        {/each}
      </div>
    </section>
  {:else if $view === 'playlist'}
    <PlaylistView />
  {:else if $view === 'search'}
     <h1 class="text-3xl font-bold">Zoeken</h1>
     <input type="text" placeholder="Wat wil je luisteren?" class="w-full max-w-md mt-4 p-3 rounded-full bg-white text-black font-medium focus:outline-none" />
  {/if}
</div>
