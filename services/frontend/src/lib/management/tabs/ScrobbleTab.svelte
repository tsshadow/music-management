<script >
  import { t, format } from '../../i18n/index.js';
  import { onDestroy } from 'svelte';
  import { RefreshCw } from '@lucide/svelte';
  
  export let API_BASE;
  export let getHeaders;
  export let users;
  export let latestImports;
  export let importMumaUser;
  export let importLbUser;
  export let isImporting;
  export let lbUsername;
  export let onMessage;
  export let onError;
  export let onSelectUser;
  export let fetchLatestImports;

  // The import-progress poll. Kept here rather than in a local so leaving the tab can stop it:
  // otherwise it kept polling MuMa every three seconds for as long as the page stayed open.
  let pollInterval = null;

  /** Stops the import-progress poll, if one is running. */
  function stopPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = null;
  }

  onDestroy(stopPolling);

  async function startLbImport() {
    if (!importMumaUser) return;
    isImporting = true;
    try {
      const body = { username: importMumaUser };
      if (importLbUser) {
        body.lb_username = importLbUser;
      }

      const res = await fetch(`${API_BASE}/api/scrobble/import/listenbrainz`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(body)
      });
      if (res.ok) {
        const data = await res.json();
        onMessage($t('management.scrobble.importStarted', { name: data.lb_username || $t('management.scrobble.linkedAccount') }));
        fetchLatestImports();
        // Poll for updates every 3 seconds while active
        stopPolling();
        pollInterval = setInterval(async () => {
          await fetchLatestImports();
          const active = latestImports.some(i => i.status === 'running' || i.status === 'pending');
          if (!active) {
            stopPolling();
            isImporting = false;
          }
        }, 3000);
      } else {
        onError($t('management.scrobble.startFailed'));
        isImporting = false;
      }
    } catch {
      onError($t('management.scrobble.startNetworkError'));
      isImporting = false;
    }
  }
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
  <header>
    <h2 class="text-4xl font-extrabold mb-2">📻 {$t('management.scrobble.title')}</h2>
    <p class="text-muma-spotify-text">{$t('management.scrobble.subtitle')}</p>
  </header>

  <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
    <!-- Import Form -->
    <div class="bg-muma-spotify-panel p-6 rounded-xl border border-white/5">
      <h3 class="text-xl font-bold mb-6 flex items-center gap-2">
        <RefreshCw class="text-brand {isImporting ? 'animate-spin' : ''}" /> {$t('management.scrobble.import')}
      </h3>
      <form on:submit|preventDefault={startLbImport} class="space-y-4">
        <div>
          <label for="muma-user" class="block text-sm font-bold text-muma-spotify-text mb-2">{$t('management.scrobble.mumaUser')}</label>
          <select 
            id="muma-user" 
            bind:value={importMumaUser}
            on:change={async () => {
              const user = users.find(u => u.username === importMumaUser);
              if (user) {
                await onSelectUser(user);
                // After selecting user, the parent should update lbUsername
                // This might need a tick or reactive update
              }
            }}
            class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-3 focus:outline-none focus:border-brand transition-colors"
          >
            <option value="">{$t('management.scrobble.pickUser')}</option>
            {#each users as user (user.username)}
              <option value={user.username}>{user.username}</option>
            {/each}
          </select>
        </div>
        <div>
          <label for="lb-user" class="block text-sm font-bold text-muma-spotify-text mb-2">{$t('management.scrobble.lbUsername')}</label>
          <div class="relative">
            <input 
              type="text" 
              id="lb-user" 
              bind:value={importLbUser}
              placeholder={lbUsername ? $t('management.scrobble.linkedPlaceholder', { name: lbUsername }) : "demo-user"}
              class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-3 focus:outline-none focus:border-brand transition-colors"
            />
            {#if !importLbUser && lbUsername}
              <span class="absolute right-3 top-3 text-xs text-brand font-bold">{$t('management.scrobble.linked')}</span>
            {/if}
          </div>
          <p class="text-[10px] text-muma-spotify-text mt-1 italic">
            {$t('management.scrobble.optionalIfLinked')}
          </p>
        </div>
        <button 
          type="submit" 
          disabled={isImporting || !importMumaUser}
          class="w-full bg-brand text-black font-extrabold py-3 rounded-full hover:scale-105 transition-transform disabled:opacity-50 disabled:hover:scale-100"
        >
          {isImporting ? $t('management.scrobble.importing') : $t('management.scrobble.startImport')}
        </button>
      </form>
    </div>

    <!-- Recent Imports -->
    <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
      <h3 class="p-6 text-xl font-bold bg-black/20 flex justify-between items-center">
        {$t('management.scrobble.recentImports')}
        <button on:click={fetchLatestImports} class="text-muma-spotify-text hover:text-white transition-colors">
          <RefreshCw size={16} />
        </button>
      </h3>
      <div class="overflow-x-auto">
        <table class="w-full text-left">
          <thead class="bg-black/20 text-xs uppercase text-muma-spotify-text">
            <tr>
              <th class="p-4">{$t('management.scrobble.user')}</th>
              <th class="p-4">{$t('management.health.status')}</th>
              <th class="p-4">{$t('management.scrobble.progress')}</th>
              <th class="p-4 text-right">{$t('management.scrobble.started')}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-muma-spotify-panel/30 text-sm">
            {#each latestImports as imp (imp.started_at)}
              <tr class="hover:bg-white/5 transition-colors">
                <td class="p-4">
                  <div class="font-bold">{imp.username}</div>
                  <div class="text-xs text-muma-spotify-text">LB: {imp.lb_username}</div>
                </td>
                <td class="p-4">
                  <span class="px-2 py-1 rounded-full text-[10px] font-bold uppercase
                    {imp.status === 'completed' ? 'bg-brand text-black' : 
                     imp.status === 'running' ? 'bg-blue-500 text-white' : 
                     imp.status === 'failed' ? 'bg-red-500 text-white' : 'bg-muma-spotify-panel text-white'}">
                    {imp.status}
                  </span>
                </td>
                <td class="p-4">
                  <div class="w-full bg-muma-spotify-dark rounded-full h-1.5 mb-1">
                    <div class="bg-brand h-1.5 rounded-full" style="width: {imp.total_found > 0 ? (imp.processed / imp.total_found) * 100 : 0}%"></div>
                  </div>
                  <div class="text-[10px] text-muma-spotify-text">{imp.processed} / {imp.total_found}</div>
                </td>
                <td class="p-4 text-right text-xs text-muma-spotify-text">
                  {$format.dateTime(imp.started_at)}
                </td>
              </tr>
            {/each}
            {#if latestImports.length === 0}
              <tr>
                <td colspan="4" class="p-8 text-center text-muma-spotify-text italic">{$t('management.scrobble.noHistory')}</td>
              </tr>
            {/if}
          </tbody>
        </table>
      </div>
    </div>
  </div>
</section>
