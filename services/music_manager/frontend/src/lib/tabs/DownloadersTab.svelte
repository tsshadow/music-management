<script lang="ts">
  import { Cloud, ExternalLink, Trash2, Plus, Search, Youtube } from 'lucide-svelte';
  
  export let API_BASE: string;
  export let getHeaders: () => any;
  export let accounts: any[];
  export let youtubeAccounts: any[];
  export let onMessage: (msg: string) => void;
  export let onError: (err: string) => void;
  export let refreshDownloaders: () => Promise<void>;

  let downloaderSubTab = 'soundcloud';
  let newAccountName = '';
  let newAccountId = '';

  async function addAccount() {
    if (!newAccountName) return;
    try {
      const res = await fetch(`${API_BASE}/api/soundcloud`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ name: newAccountName, id: newAccountId || null })
      });
      if (res.ok) {
        onMessage("Account toegevoegd!");
        newAccountName = '';
        newAccountId = '';
        refreshDownloaders();
      }
    } catch (err) {
      onError("Kon account niet toevoegen.");
    }
  }

  async function deleteSoundcloudAccount(name: string) {
    if (!confirm(`Weet je zeker dat je ${name} wilt verwijderen?`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/soundcloud/${name}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage("Account verwijderd.");
        refreshDownloaders();
      }
    } catch (err) {
      onError("Kon account niet verwijderen.");
    }
  }

  async function addYoutubeAccount() {
    if (!newAccountName) return;
    try {
      const res = await fetch(`${API_BASE}/api/youtube`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ name: newAccountName })
      });
      if (res.ok) {
        onMessage("YouTube kanaal toegevoegd!");
        newAccountName = '';
        refreshDownloaders();
      }
    } catch (err) {
      onError("Kon kanaal niet toevoegen.");
    }
  }

  async function deleteYoutubeAccount(name: string) {
    if (!confirm(`Weet je zeker dat je kanaal ${name} wilt verwijderen?`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/youtube/${name}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage("Kanaal verwijderd.");
        refreshDownloaders();
      }
    } catch (err) {
      onError("Kon kanaal niet verwijderen.");
    }
  }
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
  <header>
    <h1 class="text-6xl font-extrabold mb-4 tracking-tighter">Downloaders</h1>
    <p class="text-spotify-lightgray text-lg">Beheer SoundCloud accounts en YouTube kanalen voor automatische imports.</p>
  </header>

  <div class="flex gap-6 border-b border-white border-opacity-10">
    <button 
      on:click={() => downloaderSubTab = 'soundcloud'}
      class="pb-4 font-bold text-sm transition-colors relative {downloaderSubTab === 'soundcloud' ? 'text-white' : 'text-spotify-lightgray hover:text-white'}"
    >
      SoundCloud
      {#if downloaderSubTab === 'soundcloud'}
        <div class="absolute bottom-0 left-0 right-0 h-1 bg-spotify-green rounded-full animate-in fade-in duration-300"></div>
      {/if}
    </button>
    <button 
      on:click={() => downloaderSubTab = 'youtube'}
      class="pb-4 font-bold text-sm transition-colors relative {downloaderSubTab === 'youtube' ? 'text-white' : 'text-spotify-lightgray hover:text-white'}"
    >
      YouTube
      {#if downloaderSubTab === 'youtube'}
        <div class="absolute bottom-0 left-0 right-0 h-1 bg-spotify-green rounded-full animate-in fade-in duration-300"></div>
      {/if}
    </button>
  </div>

  {#if downloaderSubTab === 'soundcloud'}
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 animate-in fade-in duration-300">
      <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5 space-y-6">
        <h3 class="text-xl font-bold flex items-center gap-2"><Plus class="text-spotify-green" /> Account Toevoegen</h3>
        <form on:submit|preventDefault={addAccount} class="space-y-4">
          <div>
            <label class="block text-xs font-bold text-spotify-lightgray uppercase mb-2">Account Slug (URL)</label>
            <input type="text" bind:value={newAccountName} placeholder="bijv: monstercat" class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-3 text-white focus:outline-none focus:border-spotify-green" />
          </div>
          <div>
            <label class="block text-xs font-bold text-spotify-lightgray uppercase mb-2">SoundCloud ID (Optioneel)</label>
            <input type="text" bind:value={newAccountId} placeholder="123456" class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-3 text-white focus:outline-none focus:border-spotify-green" />
          </div>
          <button type="submit" class="w-full bg-spotify-green text-black font-extrabold py-3 rounded-full hover:scale-105 transition-transform">TOEVOEGEN</button>
        </form>
      </div>
      <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
        <table class="w-full text-left">
          <thead class="bg-black bg-opacity-20 text-xs uppercase text-spotify-lightgray">
            <tr><th class="p-4">Account</th><th class="p-4 text-right">Acties</th></tr>
          </thead>
          <tbody class="divide-y divide-spotify-gray divide-opacity-30">
            {#each accounts as account}
              <tr class="hover:bg-white hover:bg-opacity-5 transition-colors group">
                <td class="p-4 font-bold">
                  <a href="https://soundcloud.com/{account.name}" target="_blank" class="flex items-center gap-2 hover:text-spotify-green">
                    {account.name} <ExternalLink size={14} />
                  </a>
                </td>
                <td class="p-4 text-right">
                  <button on:click={() => deleteSoundcloudAccount(account.name)} class="text-spotify-lightgray hover:text-red-500">
                    <Trash2 size={16} />
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {:else if downloaderSubTab === 'youtube'}
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 animate-in fade-in duration-300">
      <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5 space-y-6">
        <h3 class="text-xl font-bold mb-6 flex items-center gap-2"><Search class="text-spotify-green" /> Snel Toevoegen</h3>
        <form on:submit|preventDefault={addYoutubeAccount} class="space-y-4">
          <div class="flex gap-2">
            <input type="text" bind:value={newAccountName} placeholder="Channel Handle of ID..." class="flex-1 bg-spotify-dark border border-spotify-gray rounded-md p-3 text-white focus:outline-none focus:border-spotify-green" />
            <button type="submit" class="bg-spotify-green text-black font-extrabold px-6 rounded-md hover:scale-105 transition-transform">ADD</button>
          </div>
          <p class="text-xs text-spotify-lightgray italic">Voeg een kanaal toe aan de automatische scanner.</p>
        </form>

        <div class="pt-6 border-t border-white border-opacity-5">
          <h3 class="text-xl font-bold mb-4 flex items-center gap-2"><Youtube class="text-red-500" /> Handmatig Downloaden</h3>
          <div class="flex gap-2">
            <input type="text" placeholder="YouTube Video URL..." class="flex-1 bg-spotify-dark border border-spotify-gray rounded-md p-3 text-white focus:outline-none focus:border-spotify-green" />
            <button class="bg-white text-black font-extrabold px-6 rounded-md hover:scale-105 transition-transform">FETCH</button>
          </div>
        </div>
      </div>
      <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
        <table class="w-full text-left">
          <thead class="bg-black bg-opacity-20 text-xs uppercase text-spotify-lightgray">
            <tr><th class="p-4">Kanaal</th><th class="p-4 text-right">Acties</th></tr>
          </thead>
          <tbody class="divide-y divide-spotify-gray divide-opacity-30">
            {#each youtubeAccounts as account}
              <tr class="hover:bg-white hover:bg-opacity-5 transition-colors group">
                <td class="p-4 font-bold">
                  <a href="https://youtube.com/{account.name.startsWith('@') ? account.name : 'channel/'+account.name}" target="_blank" class="flex items-center gap-2 hover:text-spotify-green">
                    {account.name} <ExternalLink size={14} />
                  </a>
                </td>
                <td class="p-4 text-right">
                  <button on:click={() => deleteYoutubeAccount(account.name)} class="text-spotify-lightgray hover:text-red-500">
                    <Trash2 size={16} />
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {/if}
</section>
