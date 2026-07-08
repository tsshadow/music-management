<script lang="ts">
  import { onMount } from 'svelte';
  import { RefreshCw, Plus, Trash2, Users, Key, Radio, Database } from 'lucide-svelte';
  
  export let users: any[];
  export let selectedUser: any;
  export let API_BASE: string;
  export let getHeaders: () => any;
  export let fetchUsers: () => Promise<void>;
  export let onMessage: (msg: string) => void;
  export let onError: (err: string) => void;
  export let onSelectUser: (user: any) => void;
  export let navigateToScrobbleImport: (user: string, lbUser: string) => void;

  let newUsername = '';
  let newDisplayName = '';
  let userPassword = '';
  let lbUsername = '';
  let lbToken = '';
  let userLBAccount: any = null;

  async function addUser() {
    if (!newUsername) return;
    try {
      const res = await fetch(`${API_BASE}/api/users`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          username: newUsername,
          display_name: newDisplayName,
          password: userPassword
        })
      });
      if (res.ok) {
        onMessage(`Gebruiker ${newUsername} toegevoegd!`);
        newUsername = '';
        newDisplayName = '';
        userPassword = '';
        fetchUsers();
      } else {
        const data = await res.json();
        onError(data.detail || "Kon gebruiker niet toevoegen.");
      }
    } catch (err) {
      onError("Netwerkfout bij toevoegen gebruiker.");
    }
  }

  async function deleteUser(user: any) {
    if (!confirm(`Weet je zeker dat je gebruiker ${user.username} wilt verwijderen? Dit verwijdert hem ook uit de LMS.`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/users/${user.id}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage(`Gebruiker ${user.username} verwijderd.`);
        if (selectedUser?.id === user.id) onSelectUser(null);
        fetchUsers();
      } else {
        onError("Kon gebruiker niet verwijderen.");
      }
    } catch (err) {
      onError("Netwerkfout bij verwijderen gebruiker.");
    }
  }

  async function updateLBAccount() {
    if (!selectedUser || !lbUsername || !lbToken) return;
    try {
      const res = await fetch(`${API_BASE}/api/users/${selectedUser.id}/listenbrainz`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          lb_username: lbUsername,
          lb_token: lbToken
        })
      });
      if (res.ok) {
        onMessage("ListenBrainz account gekoppeld!");
        fetchLBAccount();
      } else {
        onError("Kon ListenBrainz account niet koppelen.");
      }
    } catch (err) {
      onError("Netwerkfout bij koppelen account.");
    }
  }

  async function updatePassword() {
    if (!selectedUser || !userPassword) return;
    try {
      const res = await fetch(`${API_BASE}/api/users/${selectedUser.id}/password`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ password: userPassword })
      });
      if (res.ok) {
        onMessage("Wachtwoord bijgewerkt!");
        userPassword = '';
      } else {
        onError("Kon wachtwoord niet bijwerken.");
      }
    } catch (err) {
      onError("Netwerkfout bij bijwerken wachtwoord.");
    }
  }

  async function syncLMSUsers() {
    try {
      const res = await fetch(`${API_BASE}/api/users/sync/lms`, { 
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        onMessage(`Sync voltooid! ${data.synced} gebruikers verwerkt.`);
        fetchUsers();
      } else {
        onError("Sync mislukt.");
      }
    } catch (err) {
      onError("Netwerkfout bij sync.");
    }
  }

  async function syncLMSDbUsers() {
    try {
      const res = await fetch(`${API_BASE}/api/users/sync/lms-db`, { 
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        onMessage(`Database sync voltooid! ${data.synced} gebruikers verwerkt.`);
        fetchUsers();
      } else {
        onError("Sync mislukt.");
      }
    } catch (err) {
      onError("Netwerkfout bij sync.");
    }
  }

  async function fetchLBAccount() {
    if (!selectedUser) return;
    try {
      const res = await fetch(`${API_BASE}/api/users/${selectedUser.id}/listenbrainz`, {
        headers: getHeaders()
      });
      if (res.ok) {
        userLBAccount = await res.json();
        lbUsername = userLBAccount.lb_username || '';
        lbToken = userLBAccount.lb_token || '';
      } else {
        userLBAccount = null;
        lbUsername = '';
        lbToken = '';
      }
    } catch (err) {
      console.error(err);
    }
  }

  $: if (selectedUser) {
    fetchLBAccount();
    userPassword = '';
  }
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
  <header>
    <h2 class="text-4xl font-extrabold mb-2">👥 User Management</h2>
    <p class="text-spotify-lightgray">Beheer systeemgebruikers en hun externe account koppelingen.</p>
  </header>

  <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
    <!-- User List -->
    <div class="lg:col-span-1 space-y-6">
      <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
        <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20 flex justify-between items-center">
          Gebruikers
          <div class="flex gap-2">
            <button 
              on:click={syncLMSUsers} 
              title="Sync van LMS"
              class="text-spotify-lightgray hover:text-spotify-green transition-colors"
            >
              <RefreshCw size={16} />
            </button>
            <button 
              on:click={fetchUsers} 
              title="Verversen"
              class="text-spotify-lightgray hover:text-white transition-colors"
            >
              <RefreshCw size={16} class="rotate-90" />
            </button>
          </div>
        </h3>
        <div class="max-h-[400px] overflow-y-auto">
          <table class="w-full text-left text-sm">
            <tbody class="divide-y divide-spotify-gray divide-opacity-30">
              {#each users as user}
                <tr 
                  class="hover:bg-white hover:bg-opacity-5 cursor-pointer transition-colors {selectedUser?.id === user.id ? 'bg-spotify-gray' : ''}"
                  on:click={() => onSelectUser(user)}
                >
                  <td class="p-4">
                    <div class="flex justify-between items-center">
                      <div>
                        <div class="font-bold {selectedUser?.id === user.id ? 'text-spotify-green' : ''}">{user.username}</div>
                        <div class="text-xs text-spotify-lightgray">{user.display_name || ''}</div>
                      </div>
                      <button 
                        on:click|stopPropagation={() => deleteUser(user)}
                        class="text-spotify-lightgray hover:text-red-500 transition-colors p-2"
                        title="Verwijder gebruiker"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>

      <!-- Add User Form -->
      <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5">
        <h3 class="text-xl font-bold mb-4 flex items-center gap-2"><Plus size={20} class="text-spotify-green" /> Gebruiker Toevoegen</h3>
        <form on:submit|preventDefault={addUser} class="space-y-4">
          <div>
            <input 
              type="text" 
              bind:value={newUsername}
              placeholder="Gebruikersnaam"
              class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-2 focus:outline-none focus:border-spotify-green transition-colors"
            />
          </div>
          <div>
            <input 
              type="text" 
              bind:value={newDisplayName}
              placeholder="Display Name (Optioneel)"
              class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-2 focus:outline-none focus:border-spotify-green transition-colors"
            />
          </div>
          <div>
            <input 
              type="password" 
              bind:value={userPassword}
              placeholder="Standaard Wachtwoord"
              class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-2 focus:outline-none focus:border-spotify-green transition-colors"
            />
          </div>
          <button type="submit" class="w-full bg-spotify-green text-black font-bold py-2 rounded-full hover:scale-105 transition-transform">
            TOEVOEGEN
          </button>
        </form>
      </div>
    </div>

    <!-- User Detail / External Accounts -->
    <div class="lg:col-span-2">
      {#if selectedUser}
        <div class="space-y-6 animate-in fade-in duration-300">
          <div class="bg-spotify-gray p-8 rounded-xl border border-white border-opacity-5">
            <div class="flex items-center gap-4 mb-8">
              <div class="w-16 h-16 bg-spotify-green rounded-full flex items-center justify-center text-black text-2xl font-bold">
                {selectedUser.username.charAt(0).toUpperCase()}
              </div>
              <div>
                <h3 class="text-3xl font-extrabold">{selectedUser.username}</h3>
                <p class="text-spotify-lightgray">{selectedUser.display_name || 'Geen display name'}</p>
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
              <!-- Password Section -->
              <div class="space-y-4">
                <h4 class="text-xl font-bold flex items-center gap-2 text-white">
                  <Key size={20} class="text-spotify-green" /> Beveiliging
                </h4>
                <div class="bg-spotify-dark p-6 rounded-xl border border-spotify-gray space-y-4">
                  <div>
                    <label class="block text-xs font-bold text-spotify-lightgray uppercase mb-1">Nieuw Wachtwoord</label>
                    <input 
                      type="password" 
                      bind:value={userPassword}
                      placeholder="••••••••"
                      class="w-full bg-spotify-gray bg-opacity-30 border border-spotify-gray rounded-md p-2 focus:outline-none focus:border-spotify-green transition-colors"
                    />
                  </div>
                  <button 
                    on:click={updatePassword}
                    disabled={!userPassword}
                    class="w-full bg-spotify-green text-black text-xs font-bold py-2 rounded-full hover:scale-105 transition-transform disabled:opacity-50"
                  >
                    WACHTWOORD OPSLAAN
                  </button>
                </div>
              </div>

              <!-- ListenBrainz Section -->
              <div class="space-y-4">
                <h4 class="text-xl font-bold flex items-center gap-2 text-white">
                  <Radio size={20} class="text-[#EB743B]" /> ListenBrainz
                </h4>
                <div class="bg-spotify-dark p-6 rounded-xl border border-spotify-gray space-y-4">
                  <div>
                    <label class="block text-xs font-bold text-spotify-lightgray uppercase mb-1">LB Username</label>
                    <input 
                      type="text" 
                      bind:value={lbUsername}
                      placeholder="ListenBrainz User"
                      class="w-full bg-spotify-gray bg-opacity-30 border border-spotify-gray rounded-md p-2 focus:outline-none focus:border-spotify-green transition-colors"
                    />
                  </div>
                  <div>
                    <label class="block text-xs font-bold text-spotify-lightgray uppercase mb-1">API Token</label>
                    <div class="relative">
                      <Key class="absolute left-2 top-2.5 text-spotify-lightgray" size={16} />
                      <input 
                        type="password" 
                        bind:value={lbToken}
                        placeholder="Token"
                        class="w-full bg-spotify-gray bg-opacity-30 border border-spotify-gray rounded-md p-2 pl-9 focus:outline-none focus:border-spotify-green transition-colors font-mono text-sm"
                      />
                    </div>
                  </div>
                  <div class="flex gap-2">
                    <button 
                      on:click={() => navigateToScrobbleImport(selectedUser.username, lbUsername)}
                      class="flex-1 bg-white text-black text-xs font-bold py-2 rounded-full hover:scale-105 transition-transform"
                    >
                      IMPORT STARTEN
                    </button>
                    <button 
                      on:click={updateLBAccount}
                      class="flex-1 bg-spotify-green text-black text-xs font-bold py-2 rounded-full hover:scale-105 transition-transform"
                    >
                      OPSLAAN
                    </button>
                  </div>
                </div>
              </div>

              <!-- LMS Settings -->
              <div class="space-y-4">
                <h4 class="text-xl font-bold flex items-center gap-2 text-white">
                  <Database size={20} class="text-spotify-green" /> LMS Integratie
                </h4>
                <div class="bg-spotify-dark p-6 rounded-xl border border-spotify-gray space-y-4">
                  <p class="text-xs text-spotify-lightgray">Synchroniseer gebruikersgegevens direct vanuit Logitech Media Server.</p>
                  <div class="flex flex-col gap-2">
                    <button 
                      on:click={syncLMSUsers}
                      class="w-full bg-white text-black text-xs font-bold py-2 rounded-full hover:scale-105 transition-transform flex items-center justify-center gap-2"
                    >
                      <RefreshCw size={14} /> SYNC VIA API (SPELERS)
                    </button>
                    <button 
                      on:click={syncLMSDbUsers}
                      class="w-full bg-spotify-green text-black text-xs font-bold py-2 rounded-full hover:scale-105 transition-transform flex items-center justify-center gap-2"
                    >
                      <Database size={14} /> SYNC VIA DATABASE (USERS)
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      {:else}
        <div class="h-full flex items-center justify-center bg-spotify-gray bg-opacity-20 rounded-xl border border-dashed border-spotify-gray p-12 text-center text-spotify-lightgray">
          <div>
            <Users size={48} class="mx-auto mb-4 opacity-20" />
            <p class="text-xl font-bold">Selecteer een gebruiker</p>
            <p>Kies een gebruiker uit de lijst om instellingen te beheren.</p>
          </div>
        </div>
      {/if}
    </div>
  </div>
</section>
