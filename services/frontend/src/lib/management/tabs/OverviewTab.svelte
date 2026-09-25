<script >
  import { t, format } from '../../i18n/index.js';
  import { ShieldCheck, Clock, Info, Activity, RefreshCw } from '@lucide/svelte';
  
  export let containers;
  export let activity;
  export let config;
  export let allNotes;
  export let selectedServiceNotes;
  export let notes;
  export let stats;
  export let fetchStats;
  export let fetchArtistImages;
</script>

<section class="space-y-8 animate-in fade-in duration-500">
  <header class="flex justify-between items-end">
    <div>
      <h1 class="text-6xl font-extrabold mb-4 tracking-tighter">{$t('management.overview.title')}</h1>
      <p class="text-muma-spotify-text text-lg">{$t('management.overview.subtitle')}</p>
    </div>
  </header>

  <!-- Status Cards -->
  <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
    <div class="bg-muma-spotify-panel p-6 rounded-xl border border-white/5">
      <div class="flex items-center gap-3 mb-4">
        <ShieldCheck class={containers.every(c => c.status === 'running') ? 'text-brand' : 'text-red-500'} />
        <h3 class="font-bold">{$t('management.overview.systemStatus')}</h3>
      </div>
      <div class="text-2xl font-extrabold">
        {containers.filter(c => c.status === 'running').length} / {containers.length} Running
      </div>
      <p class="text-xs text-muma-spotify-text mt-2">
        {#if containers.some(c => c.status !== 'running')}
          <span class="text-red-500 font-bold">{$t('management.overview.containersWithProblems', { count: containers.filter(c => c.status !== 'running').length })}</span>
        {:else}
          {$t('management.overview.allSystemsOk')}
        {/if}
      </p>
    </div>

    <div class="bg-muma-spotify-panel p-6 rounded-xl border border-white/5">
      <div class="flex items-center gap-3 mb-4">
        <Clock class="text-blue-400" />
        <h3 class="font-bold">{$t('management.overview.lastActivity')}</h3>
      </div>
      <div class="text-2xl font-extrabold">
        {activity.recent_added.length > 0 ? new Date(activity.recent_added[0].timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '-'}
      </div>
      <p class="text-xs text-muma-spotify-text mt-2">{$t('management.overview.lastTrackAdded')}</p>
    </div>

    <div class="bg-muma-spotify-panel p-6 rounded-xl border border-white/5">
      <div class="flex items-center gap-3 mb-4">
        <Info class="text-brand" />
        <h3 class="font-bold">{$t('management.overview.version')}</h3>
      </div>
      <div class="text-2xl font-extrabold">{config.version}</div>
      <p class="text-xs text-muma-spotify-text mt-2">Service: music-manager</p>
    </div>
  </div>

  <!-- System Alerts (if any) -->
  {#if containers.some(c => c.status !== 'running')}
    <div class="bg-red-500/10 border border-red-500 rounded-xl p-4 flex items-center gap-4 animate-in shake duration-500">
      <ShieldCheck size={32} class="text-red-500" />
      <div>
        <h3 class="font-bold text-red-500 text-sm uppercase tracking-wider">{$t('management.overview.alert')}</h3>
        <p class="text-sm text-red-200">
          {$t('management.overview.servicesOffline', { count: containers.filter(c => c.status !== 'running').length })}
          <span class="font-bold font-mono">{containers.filter(c => c.status !== 'running').map(c => c.name).join(', ')}</span>
        </p>
      </div>
    </div>
  {/if}

  <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
    <!-- Recent Activity Mini List -->
    <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
      <h3 class="p-6 text-xl font-bold bg-black/20 flex items-center gap-2">
        <Activity size={20} class="text-brand" /> {$t('management.overview.recentActivity')}
      </h3>
      <div class="max-h-[300px] overflow-y-auto">
        <ul class="divide-y divide-muma-spotify-panel/30">
          {#each activity.recent_added.slice(0, 5) as item, i (i)}
            <li class="p-4 hover:bg-white/5 flex justify-between items-center gap-4">
              <div class="truncate">
                <div class="font-bold text-sm truncate">{item.title || (item.file_path ? item.file_path.split('/').pop() : $t('management.overview.unknown'))}</div>
                <div class="text-xs text-muma-spotify-text truncate">{item.artist || item.source}</div>
              </div>
              <div class="text-[10px] text-muma-spotify-text whitespace-nowrap text-right">
                {$format.date(item.timestamp)}
              </div>
            </li>
          {/each}
          {#if activity.recent_added.length === 0}
            <li class="p-8 text-center text-muma-spotify-text italic">{$t('management.overview.noActivity')}</li>
          {/if}
        </ul>
      </div>
    </div>

    <!-- Quick Release Notes -->
    <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden flex flex-col">
      <h3 class="p-6 text-xl font-bold bg-black/20 flex items-center justify-between">
        <div class="flex items-center gap-2"><RefreshCw size={20} class="text-blue-400" /> Release Notes</div>
        <select 
          bind:value={selectedServiceNotes}
          class="bg-muma-spotify-dark border border-white/10 rounded-md p-1 text-xs text-white focus:outline-none focus:border-brand"
        >
          {#each Object.keys(allNotes) as service (service)}
            <option value={service}>{service.replace('-', ' ')}</option>
          {/each}
        </select>
      </h3>
      <div class="p-6 overflow-y-auto flex-1 max-h-[300px] prose prose-invert prose-sm">
        {#if selectedServiceNotes === 'control-center'}
          <h4 class="text-brand">Version {config.version}</h4>
          {@html notes.release_notes}
        {:else if allNotes[selectedServiceNotes]}
          <h4 class="text-brand">Version {allNotes[selectedServiceNotes].version}</h4>
          {@html allNotes[selectedServiceNotes].notes}
        {/if}
      </div>
    </div>
  </div>

  <!-- Collection and listening figures, moved here from the Statistics tab.
       Library-specific breakdowns live in the Library Browser, where they follow
       the active filter instead of being collection-wide only. -->
  <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
    <div class="bg-muma-spotify-panel p-4 rounded-xl border border-white/5">
      <div class="text-muma-spotify-text text-[10px] font-bold uppercase mb-1">{$t('management.overview.totalTracks')}</div>
      <div class="text-2xl font-extrabold text-brand">{$format.number(stats.total_tracks)}</div>
    </div>
    <div class="bg-muma-spotify-panel p-4 rounded-xl border border-white/5">
      <div class="text-muma-spotify-text text-[10px] font-bold uppercase mb-1">{$t('management.overview.totalArtists')}</div>
      <div class="text-2xl font-extrabold text-white">{$format.number(stats.total_artists)}</div>
    </div>
    <div class="bg-muma-spotify-panel p-4 rounded-xl border border-white/5">
      <div class="text-muma-spotify-text text-[10px] font-bold uppercase mb-1">{$t('management.overview.totalScrobbles')}</div>
      <div class="text-2xl font-extrabold text-blue-400">{$format.number(stats.total_scrobbles)}</div>
    </div>
    <div class="bg-muma-spotify-panel p-4 rounded-xl border border-white/5">
      <div class="text-muma-spotify-text text-[10px] font-bold uppercase mb-1">{$t('management.overview.matchRate')}</div>
      <div class="text-2xl font-extrabold {stats.match_rate > 80 ? 'text-brand' : 'text-yellow-500'}">{stats.match_rate}%</div>
    </div>
  </div>

  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
    <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
      <h3 class="p-4 text-lg font-bold bg-black/20">{$t('management.overview.popularGenres')}</h3>
      <div class="p-4 space-y-3">
        {#each stats.top_genres as genre (genre.genre)}
          <div class="space-y-1">
            <div class="flex justify-between text-sm font-bold">
              <span>{genre.genre}</span>
              <span class="text-muma-spotify-text tabular-nums">{$format.number(genre.count)}</span>
            </div>
            <div class="w-full bg-muma-spotify-dark rounded-full h-1.5">
              <div class="bg-brand h-1.5 rounded-full" style="width: {stats.top_genres.length > 0 ? (genre.count / stats.top_genres[0].count) * 100 : 0}%"></div>
            </div>
          </div>
        {/each}
        {#if stats.top_genres.length === 0}
          <p class="text-xs text-muma-spotify-text italic">{$t('management.overview.noGenresIndexed')}</p>
        {/if}
      </div>
    </div>

    <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
      <h3 class="p-4 text-lg font-bold bg-black/20">{$t('management.overview.newInLibrary')}</h3>
      <table class="w-full text-left">
        <tbody class="divide-y divide-muma-spotify-panel/30">
          {#each stats.recently_added as track (track.title + track.artist)}
            <tr>
              <td class="p-3">
                <div class="font-bold text-sm">{track.title}</div>
                <div class="text-xs text-muma-spotify-text">{track.artist}</div>
              </td>
              <td class="p-3 text-right text-xs text-muma-spotify-text">
                {$format.date(track.created_at)}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>

  <div class="flex flex-wrap gap-3 items-center">
    <button on:click={fetchArtistImages} class="bg-white text-black font-extrabold px-5 py-2.5 rounded-full hover:scale-105 transition-transform text-sm">
      {$t('management.overview.fetchImages')}
    </button>
    <button on:click={fetchStats} class="bg-muma-spotify-panel px-5 py-2.5 rounded-full hover:bg-white/10 transition-colors text-sm font-bold">
      {$t('management.overview.refresh')}
    </button>
    <span class="text-xs text-muma-spotify-text">
      {$t('management.overview.avgTrackLength')}
      <b class="text-white">{Math.floor(stats.avg_track_duration / 60)}:{Math.floor(stats.avg_track_duration % 60).toString().padStart(2, '0')}</b>
      · Unmatched scrobbles <b class="text-yellow-500">{$format.number(stats.total_unmatched)}</b>
    </span>
  </div>
</section>
