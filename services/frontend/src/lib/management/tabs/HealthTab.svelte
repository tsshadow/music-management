<script >
  import { t } from '../../i18n/index.js';
  import { ShieldCheck, RefreshCw, Terminal, Clock, Plus, Tag } from '@lucide/svelte';
  
  export let containers;
  export let activity;
  export let API_BASE;
  export let getHeaders;
  export let refreshSystemStatus;

  let selectedContainer = '';
  let systemLogs = '';

  async function fetchLogs(name) {
    selectedContainer = name;
    systemLogs = 'Laden...';
    try {
      const res = await fetch(`${API_BASE}/api/system/logs/${name}?tail=200`, { headers: getHeaders() });
      if (res.ok) {
        const data = await res.json();
        systemLogs = data.logs;
      } else {
        systemLogs = $t('management.health.logsUnavailable');
      }
    } catch (err) {
      systemLogs = $t('management.health.logsFailed');
    }
  }
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
  <header class="flex justify-between items-end">
    <div>
      <h2 class="text-4xl font-extrabold mb-2">🛡️ {$t('management.health.title')}</h2>
      <p class="text-spotify-lightgray">{$t('management.health.subtitle')}</p>
    </div>
    <button 
      on:click={refreshSystemStatus}
      class="bg-spotify-gray hover:bg-spotify-lightgray text-white px-4 py-2 rounded-full flex items-center gap-2 transition-colors"
    >
      <RefreshCw size={16} /> {$t('common.refresh')}
    </button>
  </header>

  <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
    <!-- Container Status -->
    <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
      <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20 flex items-center gap-2">
        <ShieldCheck class="text-spotify-green" /> {$t('management.health.containers')}
      </h3>
      <div class="max-h-[500px] overflow-y-auto">
        <table class="w-full text-left">
          <thead class="bg-black bg-opacity-20 text-xs uppercase text-spotify-lightgray sticky top-0">
            <tr>
              <th class="p-4">{$t('management.health.name')}</th>
              <th class="p-4">{$t('management.health.status')}</th>
              <th class="p-4 text-right">{$t('management.health.logs')}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-spotify-gray divide-opacity-30 text-sm">
            {#each containers as container (container.name)}
              <tr class="hover:bg-white hover:bg-opacity-5 transition-colors">
                <td class="p-4">
                  <div class="font-bold">{container.name}</div>
                  <div class="text-[10px] text-spotify-lightgray truncate max-w-[200px]">{container.image}</div>
                </td>
                <td class="p-4">
                  <span class="px-2 py-1 rounded-full text-[10px] font-bold uppercase
                    {container.status === 'running' ? 'bg-spotify-green text-black' : 'bg-red-500 text-white'}">
                    {container.status}
                  </span>
                </td>
                <td class="p-4 text-right">
                  <button 
                    on:click={() => fetchLogs(container.name)}
                    class="text-spotify-lightgray hover:text-spotify-green"
                  >
                    <Terminal size={18} />
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>

    <!-- Recent Activity -->
    <div class="space-y-8">
      <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
        <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20 flex items-center gap-2">
          <Plus class="text-spotify-green" /> {$t('management.health.recentlyAdded')}
        </h3>
        <div class="max-h-[250px] overflow-y-auto">
          <ul class="divide-y divide-spotify-gray divide-opacity-30">
            {#each activity.recent_added as item (item.file_path)}
              <li class="p-4 hover:bg-white hover:bg-opacity-5 flex justify-between items-center gap-4">
                <div class="truncate">
                  <div class="font-bold text-sm truncate">{item.title || item.file_path.split('/').pop()}</div>
                  <div class="text-xs text-spotify-lightgray truncate">{item.artist || item.source}</div>
                </div>
                <div class="text-[10px] text-spotify-lightgray whitespace-nowrap text-right">
                  <Clock size={10} class="inline mb-0.5" /> {new Date(item.timestamp).toLocaleString()}
                </div>
              </li>
            {/each}
          </ul>
        </div>
      </div>

      <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
        <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20 flex items-center gap-2">
          <Tag class="text-spotify-green" /> {$t('management.health.recentlyTagged')}
        </h3>
        <div class="max-h-[250px] overflow-y-auto">
          <ul class="divide-y divide-spotify-gray divide-opacity-30">
            {#each activity.recent_tagged as item (item.file_path)}
              <li class="p-4 hover:bg-white hover:bg-opacity-5 flex justify-between items-center gap-4">
                <div class="truncate">
                  <div class="font-bold text-sm truncate">{item.title || item.file_path.split('/').pop()}</div>
                  <div class="text-xs text-spotify-lightgray truncate">{item.artist || item.source}</div>
                </div>
                <div class="text-[10px] text-spotify-lightgray whitespace-nowrap text-right">
                  <Clock size={10} class="inline mb-0.5" /> {new Date(item.timestamp).toLocaleString()}
                </div>
              </li>
            {/each}
          </ul>
        </div>
      </div>
    </div>
  </div>

  <!-- Logs Viewer -->
  {#if selectedContainer}
    <div class="bg-black rounded-xl border border-spotify-gray overflow-hidden flex flex-col h-[500px] animate-in slide-in-from-bottom-4">
      <div class="bg-spotify-gray p-4 flex justify-between items-center border-b border-white border-opacity-10">
        <div class="flex items-center gap-2 font-bold text-sm">
          <Terminal size={16} class="text-spotify-green" /> 
          {$t('management.health.logsFor', { container: selectedContainer })}
        </div>
        <div class="flex items-center gap-4">
          <button on:click={() => fetchLogs(selectedContainer)} class="text-spotify-lightgray hover:text-white transition-colors">
            <RefreshCw size={14} />
          </button>
          <button on:click={() => selectedContainer = ''} class="text-spotify-lightgray hover:text-white text-xl leading-none">&times;</button>
        </div>
      </div>
      <pre class="p-4 text-xs font-mono text-spotify-lightgray overflow-auto flex-1 bg-black bg-opacity-50">
        {systemLogs}
      </pre>
    </div>
  {/if}
</section>
