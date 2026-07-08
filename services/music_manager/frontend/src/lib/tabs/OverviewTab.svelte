<script lang="ts">
  import { ShieldCheck, Clock, Info, Activity, RefreshCw } from 'lucide-svelte';
  
  export let containers: any[];
  export let activity: any;
  export let config: any;
  export let allNotes: any;
  export let selectedServiceNotes: string;
  export let notes: any;
  export let onNavigateToStats: () => void;
</script>

<section class="space-y-8 animate-in fade-in duration-500">
  <header class="flex justify-between items-end">
    <div>
      <h1 class="text-6xl font-extrabold mb-4 tracking-tighter">MuMa Overview</h1>
      <p class="text-spotify-lightgray text-lg">Welkom terug! Hier is een overzicht van je systeem status.</p>
    </div>
  </header>

  <!-- Status Cards -->
  <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
    <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5">
      <div class="flex items-center gap-3 mb-4">
        <ShieldCheck class={containers.every(c => c.status === 'running') ? 'text-spotify-green' : 'text-red-500'} />
        <h3 class="font-bold">Systeem Status</h3>
      </div>
      <div class="text-2xl font-extrabold">
        {containers.filter(c => c.status === 'running').length} / {containers.length} Running
      </div>
      <p class="text-xs text-spotify-lightgray mt-2">
        {#if containers.some(c => c.status !== 'running')}
          <span class="text-red-500 font-bold">{containers.filter(c => c.status !== 'running').length} containers hebben problemen.</span>
        {:else}
          Alle systemen werken naar behoren.
        {/if}
      </p>
    </div>

    <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5">
      <div class="flex items-center gap-3 mb-4">
        <Clock class="text-blue-400" />
        <h3 class="font-bold">Laatste Activiteit</h3>
      </div>
      <div class="text-2xl font-extrabold">
        {activity.recent_added.length > 0 ? new Date(activity.recent_added[0].timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '-'}
      </div>
      <p class="text-xs text-spotify-lightgray mt-2">Laatste track toegevoegd.</p>
    </div>

    <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5">
      <div class="flex items-center gap-3 mb-4">
        <Info class="text-spotify-green" />
        <h3 class="font-bold">MuMa Versie</h3>
      </div>
      <div class="text-2xl font-extrabold">{config.version}</div>
      <p class="text-xs text-spotify-lightgray mt-2">Service: music-manager</p>
    </div>
  </div>

  <!-- System Alerts (if any) -->
  {#if containers.some(c => c.status !== 'running')}
    <div class="bg-red-500 bg-opacity-10 border border-red-500 rounded-xl p-4 flex items-center gap-4 animate-in shake duration-500">
      <ShieldCheck size={32} class="text-red-500" />
      <div>
        <h3 class="font-bold text-red-500 text-sm uppercase tracking-wider">Systeem Alert</h3>
        <p class="text-sm text-red-200">
          {containers.filter(c => c.status !== 'running').length} service(s) zijn momenteel offline: 
          <span class="font-bold font-mono">{containers.filter(c => c.status !== 'running').map(c => c.name).join(', ')}</span>
        </p>
      </div>
    </div>
  {/if}

  <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
    <!-- Recent Activity Mini List -->
    <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
      <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20 flex items-center gap-2">
        <Activity size={20} class="text-spotify-green" /> Recente Activiteit
      </h3>
      <div class="max-h-[300px] overflow-y-auto">
        <ul class="divide-y divide-spotify-gray divide-opacity-30">
          {#each activity.recent_added.slice(0, 5) as item}
            <li class="p-4 hover:bg-white hover:bg-opacity-5 flex justify-between items-center gap-4">
              <div class="truncate">
                <div class="font-bold text-sm truncate">{item.title || item.file_path.split('/').pop()}</div>
                <div class="text-xs text-spotify-lightgray truncate">{item.artist || item.source}</div>
              </div>
              <div class="text-[10px] text-spotify-lightgray whitespace-nowrap text-right">
                {new Date(item.timestamp).toLocaleDateString()}
              </div>
            </li>
          {/each}
          {#if activity.recent_added.length === 0}
            <li class="p-8 text-center text-spotify-lightgray italic">Geen recente activiteit gevonden.</li>
          {/if}
        </ul>
      </div>
      <div class="p-4 bg-black bg-opacity-20 text-center">
         <button on:click={onNavigateToStats} class="text-xs font-bold text-spotify-lightgray hover:text-white uppercase tracking-widest">Bekijk alle statistieken</button>
      </div>
    </div>

    <!-- Quick Release Notes -->
    <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden flex flex-col">
      <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20 flex items-center justify-between">
        <div class="flex items-center gap-2"><RefreshCw size={20} class="text-blue-400" /> Release Notes</div>
        <select 
          bind:value={selectedServiceNotes}
          class="bg-spotify-dark border border-white border-opacity-10 rounded-md p-1 text-xs text-white focus:outline-none focus:border-spotify-green"
        >
          {#each Object.keys(allNotes) as service}
            <option value={service}>{service.replace('-', ' ')}</option>
          {/each}
        </select>
      </h3>
      <div class="p-6 overflow-y-auto flex-1 max-h-[300px] prose prose-invert prose-sm">
        {#if selectedServiceNotes === 'control-center'}
          <h4 class="text-spotify-green">Version {config.version}</h4>
          {@html notes.release_notes}
        {:else if allNotes[selectedServiceNotes]}
          <h4 class="text-spotify-green">Version {allNotes[selectedServiceNotes].version}</h4>
          {@html allNotes[selectedServiceNotes].notes}
        {/if}
      </div>
    </div>
  </div>
</section>
