<script lang="ts">
  import { Search, Image, RefreshCw, User, Loader2 } from 'lucide-svelte';
  
  export let API_BASE: string;
  export let artistImageSearch: string;
  export let artistsWithImages: any[];
  export let allArtists: any[];
  export let searchArtistImages: () => Promise<void>;
  export let fetchArtistImages: () => Promise<void>;
  export let manualFetchImage: (artistId: number) => Promise<void>;
  export let fetchProgress: any;
  export let imageStats: any;

  $: progressPercent = fetchProgress.total > 0 ? Math.round((fetchProgress.current / fetchProgress.total) * 100) : 0;
</script>

<section class="space-y-8 animate-in fade-in duration-500">
  <header class="flex flex-col md:flex-row md:items-end justify-between gap-6">
    <div>
      <h1 class="text-6xl font-extrabold mb-4 tracking-tighter">Artist Images</h1>
      <p class="text-spotify-lightgray text-lg">Beheer en download afbeeldingen voor artiesten in je bibliotheek.</p>
    </div>
    
    <div class="flex items-center gap-4">
      <div class="text-right">
        <p class="text-xs text-spotify-lightgray uppercase tracking-widest font-bold">Bibliotheek Status</p>
        <p class="text-2xl font-black text-white">
          <span class="text-spotify-green">{imageStats.artists_with_images}</span>
          <span class="text-spotify-lightgray mx-1">/</span>
          {imageStats.total_artists} <span class="text-sm font-normal text-spotify-lightgray">artiesten</span>
        </p>
      </div>
      
      <button 
        on:click={fetchArtistImages} 
        disabled={fetchProgress.active}
        class="bg-white text-black font-extrabold px-6 py-3 rounded-full hover:scale-105 active:scale-95 transition-all flex items-center gap-2 shadow-xl shadow-white/5 disabled:opacity-50 disabled:scale-100"
      >
        {#if fetchProgress.active}
          <Loader2 size={20} class="animate-spin" />
          SCANNEN...
        {:else}
          <RefreshCw size={20} />
          RESCAN
        {/if}
      </button>
    </div>
  </header>

  {#if fetchProgress.active || fetchProgress.status === 'completed'}
    <div class="bg-spotify-gray bg-opacity-40 p-6 rounded-2xl border border-white border-opacity-10 shadow-2xl animate-in slide-in-from-top-4 duration-500">
      <div class="flex justify-between items-center mb-4">
        <div class="flex items-center gap-3">
          <div class="bg-spotify-green bg-opacity-20 p-2 rounded-lg">
            <RefreshCw size={20} class="text-spotify-green {fetchProgress.active ? 'animate-spin' : ''}" />
          </div>
          <div>
            <h3 class="font-bold text-lg">
              {#if fetchProgress.active}
                Artist Images Scannen...
              {:else}
                Scan Voltooid!
              {/if}
            </h3>
            {#if fetchProgress.active && fetchProgress.last_artist}
              <p class="text-sm text-spotify-lightgray">Bezig met: <span class="text-white font-medium">{fetchProgress.last_artist}</span></p>
            {/if}
          </div>
        </div>
        <div class="text-right">
          <span class="text-2xl font-black text-spotify-green">{progressPercent}%</span>
          <p class="text-xs text-spotify-lightgray font-bold">{fetchProgress.current} / {fetchProgress.total}</p>
        </div>
      </div>
      
      <div class="w-full bg-black bg-opacity-40 h-3 rounded-full overflow-hidden border border-white border-opacity-5">
        <div 
          class="h-full bg-gradient-to-r from-spotify-green to-emerald-400 transition-all duration-500 ease-out relative"
          style="width: {progressPercent}%"
        >
          <div class="absolute inset-0 bg-white bg-opacity-20 animate-pulse"></div>
        </div>
      </div>
    </div>
  {/if}

  <div class="space-y-6">
    <div class="relative group max-w-xl">
      <div class="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-spotify-lightgray group-focus-within:text-spotify-green transition-colors">
        <Search size={20} />
      </div>
      <input 
        type="text" 
        bind:value={artistImageSearch}
        on:input={searchArtistImages}
        placeholder="Zoek artiest..." 
        class="w-full bg-spotify-gray bg-opacity-50 border border-white border-opacity-10 rounded-full py-4 pl-12 pr-4 text-white focus:outline-none focus:border-spotify-green focus:bg-opacity-80 transition-all placeholder:text-spotify-lightgray text-lg shadow-lg"
      />
    </div>

    {#if artistsWithImages.length > 0}
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6">
        {#each artistsWithImages as artist}
          <div class="bg-spotify-gray bg-opacity-30 rounded-xl overflow-hidden border border-white border-opacity-5 hover:bg-opacity-50 transition-all group shadow-lg">
            <div class="aspect-square bg-black flex items-center justify-center overflow-hidden relative">
              <img 
                src={`${API_BASE}/api/artists/${encodeURIComponent(artist.name)}/image`} 
                alt={artist.name}
                class="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500"
                on:error={(e) => e.target.src = 'https://via.placeholder.com/300?text=Geen+Afbeelding'}
              />
              <div class="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-20 transition-opacity"></div>
              
              <button 
                on:click={() => manualFetchImage(artist.id)}
                class="absolute bottom-2 right-2 p-2 bg-black bg-opacity-60 rounded-full text-white opacity-0 group-hover:opacity-100 transition-opacity hover:bg-spotify-green hover:text-black"
                title="Opnieuw scannen"
              >
                <RefreshCw size={16} />
              </button>
            </div>
            <div class="p-4">
              <h3 class="font-bold truncate text-lg" title={artist.name}>{artist.name}</h3>
              <p class="text-xs text-spotify-lightgray mt-1">
                {artist.width}x{artist.height} • {artist.mime_type ? artist.mime_type.split('/')[1].toUpperCase() : 'JPG'}
              </p>
            </div>
          </div>
        {/each}
      </div>
    {/if}

    {#if artistImageSearch && allArtists.length > 0}
      <div class="mt-12">
        <h2 class="text-2xl font-bold mb-6 flex items-center gap-3">
          <User size={24} class="text-spotify-lightgray" />
          Alle Artiesten Resultaten
        </h2>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {#each allArtists.filter(a => !artistsWithImages.some(ai => ai.id === a.id)) as artist}
            <div class="bg-spotify-gray bg-opacity-20 p-4 rounded-xl border border-white border-opacity-5 flex items-center justify-between group hover:bg-opacity-30 transition-all">
              <div class="flex items-center gap-4">
                <div class="w-12 h-12 bg-black rounded-lg flex items-center justify-center text-spotify-lightgray">
                  {#if artist.primary_image_id}
                    <img 
                      src={`${API_BASE}/api/artists/${encodeURIComponent(artist.name)}/image`} 
                      alt="" 
                      class="w-full h-full object-cover rounded-lg"
                    />
                  {:else}
                    <User size={24} />
                  {/if}
                </div>
                <div>
                  <p class="font-bold text-white">{artist.name}</p>
                  <p class="text-xs text-spotify-lightgray">
                    Status: <span class={artist.image_status === 'failed' ? 'text-red-400' : 'text-spotify-lightgray'}>
                      {artist.image_status || 'Geen afbeelding'}
                    </span>
                  </p>
                </div>
              </div>
              
              <button 
                on:click={() => manualFetchImage(artist.id)}
                class="bg-white bg-opacity-10 hover:bg-white hover:text-black p-2 rounded-full transition-all"
                title="Nu scannen"
              >
                <RefreshCw size={18} />
              </button>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    {#if artistsWithImages.length === 0 && allArtists.length === 0}
      {#if artistImageSearch}
        <div class="bg-spotify-gray bg-opacity-20 p-12 rounded-xl text-center border border-dashed border-white border-opacity-10">
          <Search size={48} class="mx-auto mb-4 text-spotify-lightgray opacity-20" />
          <p class="text-spotify-lightgray text-xl font-medium">Geen artiesten gevonden met de naam "{artistImageSearch}"</p>
        </div>
      {:else}
        <div class="bg-spotify-gray bg-opacity-20 p-12 rounded-xl text-center border border-dashed border-white border-opacity-10">
          <Image size={48} class="mx-auto mb-4 text-spotify-lightgray opacity-20" />
          <p class="text-spotify-lightgray text-xl font-medium">Gebruik de zoekbalk hierboven om opgeslagen artiest afbeeldingen te bekijken.</p>
        </div>
      {/if}
    {/if}
  </div>
</section>
