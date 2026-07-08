<script lang="ts">
  import { RefreshCw, Radio } from 'lucide-svelte';
  
  export let API_BASE: string;
  export let getHeaders: () => any;
  export let users: any[];
  export let latestImports: any[];
  export let importMumaUser: string;
  export let importLbUser: string;
  export let isImporting: boolean;
  export let lbUsername: string;
  export let onMessage: (msg: string) => void;
  export let onError: (err: string) => void;
  export let onSelectUser: (user: any) => Promise<void>;
  export let fetchLatestImports: () => Promise<void>;

  async function startLbImport() {
    if (!importMumaUser) return;
    isImporting = true;
    try {
      const body: any = { username: importMumaUser };
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
        onMessage(`ListenBrainz import gestart voor ${data.lb_username || 'gekoppeld account'}!`);
        fetchLatestImports();
        // Poll for updates every 3 seconds while active
        const interval = setInterval(async () => {
          await fetchLatestImports();
          const active = latestImports.some(i => i.status === 'running' || i.status === 'pending');
          if (!active) {
            clearInterval(interval);
            isImporting = false;
          }
        }, 3000);
      } else {
        onError("Kon import niet starten.");
        isImporting = false;
      }
    } catch (err) {
      onError("Netwerkfout bij starten import.");
      isImporting = false;
    }
  }
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
  <header>
    <h2 class="text-4xl font-extrabold mb-2">📻 Scrobble Service</h2>
    <p class="text-spotify-lightgray">Beheer luistergeschiedenis en ListenBrainz imports.</p>
  </header>

  <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
    <!-- Import Form -->
    <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5">
      <h3 class="text-xl font-bold mb-6 flex items-center gap-2">
        <RefreshCw class="text-spotify-green {isImporting ? 'animate-spin' : ''}" /> ListenBrainz Import
      </h3>
      <form on:submit|preventDefault={startLbImport} class="space-y-4">
        <div>
          <label for="muma-user" class="block text-sm font-bold text-spotify-lightgray mb-2">MuMa User</label>
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
            class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-3 focus:outline-none focus:border-spotify-green transition-colors"
          >
            <option value="">Kies gebruiker...</option>
            {#each users as user}
              <option value={user.username}>{user.username}</option>
            {/each}
          </select>
        </div>
        <div>
          <label for="lb-user" class="block text-sm font-bold text-spotify-lightgray mb-2">ListenBrainz Username</label>
          <div class="relative">
            <input 
              type="text" 
              id="lb-user" 
              bind:value={importLbUser}
              placeholder={lbUsername ? `Gekoppeld: ${lbUsername}` : "teunschriks"}
              class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-3 focus:outline-none focus:border-spotify-green transition-colors"
            />
            {#if !importLbUser && lbUsername}
              <span class="absolute right-3 top-3 text-xs text-spotify-green font-bold">GEKOPPELD</span>
            {/if}
          </div>
          <p class="text-[10px] text-spotify-lightgray mt-1 italic">
            Optioneel indien al gekoppeld in User Management.
          </p>
        </div>
        <button 
          type="submit" 
          disabled={isImporting || !importMumaUser}
          class="w-full bg-spotify-green text-black font-extrabold py-3 rounded-full hover:scale-105 transition-transform disabled:opacity-50 disabled:hover:scale-100"
        >
          {isImporting ? 'IMPORT BEZIG...' : 'IMPORT STARTEN'}
        </button>
      </form>
    </div>

    <!-- Recent Imports -->
    <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
      <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20 flex justify-between items-center">
        Recente Imports
        <button on:click={fetchLatestImports} class="text-spotify-lightgray hover:text-white transition-colors">
          <RefreshCw size={16} />
        </button>
      </h3>
      <div class="overflow-x-auto">
        <table class="w-full text-left">
          <thead class="bg-black bg-opacity-20 text-xs uppercase text-spotify-lightgray">
            <tr>
              <th class="p-4">User</th>
              <th class="p-4">Status</th>
              <th class="p-4">Progress</th>
              <th class="p-4 text-right">Started</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-spotify-gray divide-opacity-30 text-sm">
            {#each latestImports as imp}
              <tr class="hover:bg-white hover:bg-opacity-5 transition-colors">
                <td class="p-4">
                  <div class="font-bold">{imp.username}</div>
                  <div class="text-xs text-spotify-lightgray">LB: {imp.lb_username}</div>
                </td>
                <td class="p-4">
                  <span class="px-2 py-1 rounded-full text-[10px] font-bold uppercase
                    {imp.status === 'completed' ? 'bg-spotify-green text-black' : 
                     imp.status === 'running' ? 'bg-blue-500 text-white' : 
                     imp.status === 'failed' ? 'bg-red-500 text-white' : 'bg-spotify-gray text-white'}">
                    {imp.status}
                  </span>
                </td>
                <td class="p-4">
                  <div class="w-full bg-spotify-dark rounded-full h-1.5 mb-1">
                    <div class="bg-spotify-green h-1.5 rounded-full" style="width: {imp.total_found > 0 ? (imp.processed / imp.total_found) * 100 : 0}%"></div>
                  </div>
                  <div class="text-[10px] text-spotify-lightgray">{imp.processed} / {imp.total_found}</div>
                </td>
                <td class="p-4 text-right text-xs text-spotify-lightgray">
                  {new Date(imp.started_at).toLocaleString()}
                </td>
              </tr>
            {/each}
            {#if latestImports.length === 0}
              <tr>
                <td colspan="4" class="p-8 text-center text-spotify-lightgray italic">Geen import geschiedenis gevonden.</td>
              </tr>
            {/if}
          </tbody>
        </table>
      </div>
    </div>
  </div>
</section>
