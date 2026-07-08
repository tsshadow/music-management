<script lang="ts">
  import { Activity, RefreshCw, Image } from 'lucide-svelte';
  
  export let stats: any;
  export let fetchStats: () => Promise<void>;
  export let fetchArtistImages: () => Promise<void>;
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
  <header class="flex flex-col md:flex-row justify-between items-start md:items-end gap-6">
    <div>
      <h2 class="text-4xl font-extrabold mb-2">📊 Bibliotheek Statistieken</h2>
      <p class="text-spotify-lightgray">Inzichten in je muziekcollectie en luistergedrag.</p>
    </div>
    <div class="flex gap-4 w-full md:w-auto">
      <button 
        on:click={fetchArtistImages} 
        class="flex-1 md:flex-none bg-white text-black font-extrabold px-6 py-3 rounded-full hover:scale-105 transition-transform flex items-center justify-center gap-2 shadow-lg shadow-white/10"
        title="Haal ontbrekende artiestafbeeldingen op van externe bronnen"
      >
        <Image size={20} class="text-black" /> IMAGES OPHALEN
      </button>
      <button on:click={fetchStats} class="bg-spotify-gray p-3 rounded-full hover:bg-white hover:bg-opacity-10 transition-colors">
        <RefreshCw size={20} />
      </button>
    </div>
  </header>

  <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
    <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5">
      <div class="text-spotify-lightgray text-xs font-bold uppercase mb-1">Totaal Tracks</div>
      <div class="text-3xl font-extrabold text-spotify-green">{stats.total_tracks.toLocaleString()}</div>
    </div>
    <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5">
      <div class="text-spotify-lightgray text-xs font-bold uppercase mb-1">Totaal Artiesten</div>
      <div class="text-3xl font-extrabold text-white">{stats.total_artists.toLocaleString()}</div>
    </div>
    <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5">
      <div class="text-spotify-lightgray text-xs font-bold uppercase mb-1">Totaal Scrobbles</div>
      <div class="text-3xl font-extrabold text-blue-400">{stats.total_scrobbles.toLocaleString()}</div>
    </div>
    <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5">
      <div class="text-spotify-lightgray text-xs font-bold uppercase mb-1">Match Rate</div>
      <div class="text-3xl font-extrabold {stats.match_rate > 80 ? 'text-spotify-green' : 'text-yellow-500'}">{stats.match_rate}%</div>
    </div>
  </div>

  <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
    <!-- Top Artists -->
    <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
      <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20">Top 10 Artiesten</h3>
      <table class="w-full text-left">
        <tbody class="divide-y divide-spotify-gray divide-opacity-30">
          {#each stats.top_artists as artist, i}
            <tr class="hover:bg-white hover:bg-opacity-5 transition-colors">
              <td class="p-4 w-12 text-spotify-lightgray font-mono">{i + 1}.</td>
              <td class="p-4 font-bold">{artist.name}</td>
              <td class="p-4 text-right text-spotify-lightgray">{artist.track_count} tracks</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <!-- Top Genres -->
    <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
      <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20">Populaire Genres</h3>
      <div class="p-6 space-y-4">
        {#each stats.top_genres as genre}
          <div class="space-y-1">
            <div class="flex justify-between text-sm font-bold">
              <span>{genre.genre}</span>
              <span class="text-spotify-lightgray">{genre.count}</span>
            </div>
            <div class="w-full bg-spotify-dark rounded-full h-2">
              <div class="bg-spotify-green h-2 rounded-full" style="width: {stats.top_genres.length > 0 ? (genre.count / stats.top_genres[0].count) * 100 : 0}%"></div>
            </div>
          </div>
        {/each}
      </div>
    </div>
  </div>

  <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
    <!-- Fun Stats -->
    <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5 space-y-4">
      <h3 class="text-xl font-bold">Leuke Weetjes</h3>
      <div class="space-y-4">
        <div class="flex justify-between items-center">
          <span class="text-spotify-lightgray">Gem. Track Lengte</span>
          <span class="font-bold">{Math.floor(stats.avg_track_duration / 60)}:{Math.floor(stats.avg_track_duration % 60).toString().padStart(2, '0')}</span>
        </div>
        <div class="flex justify-between items-center">
          <span class="text-spotify-lightgray">Albums in collectie</span>
          <span class="font-bold">{stats.total_albums || 'Onbekend'}</span>
        </div>
        <div class="flex justify-between items-center">
          <span class="text-spotify-lightgray">Unmatched Scrobbles</span>
          <span class="font-bold text-yellow-500">{stats.total_unmatched}</span>
        </div>
      </div>
    </div>

    <!-- Recently Added -->
    <div class="lg:col-span-2 bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
      <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20">Nieuw in Bibliotheek</h3>
      <table class="w-full text-left">
        <tbody class="divide-y divide-spotify-gray divide-opacity-30">
          {#each stats.recently_added as track}
            <tr class="hover:bg-white hover:bg-opacity-5 transition-colors">
              <td class="p-4">
                <div class="font-bold">{track.title}</div>
                <div class="text-xs text-spotify-lightgray">{track.artist}</div>
              </td>
              <td class="p-4 text-right text-xs text-spotify-lightgray">
                {new Date(track.created_at).toLocaleDateString()}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>
</section>
