<script >
  import { onMount } from 'svelte';
  import { RefreshCw, Plus, Trash2, Users, Key, Radio, Database, Shield, ShieldAlert, ShieldCheck, Link, Power, LogOut } from '@lucide/svelte';
  import { authParams, hasPermission, mumaApiUrl, mumaUser } from '../../store.js';

  export let users;
  export let roles = [];
  export let selectedUser;
  export let API_BASE;
  export let getHeaders;
  export let fetchUsers;
  export let onMessage;
  export let onError;
  export let onSelectUser;
  export let navigateToScrobbleImport;

  let newUsername = '';
  let newDisplayName = '';
  let newUserPassword = '';
  let updateUserPassword = '';
  let lbUsername = '';
  let lbToken = '';
  let userLBAccount = null;
  let userIdentities = [];
  let lastSelectedUserId = null;
  let mergeSecondaryId = '';
  let subsonicToken = '';
  let subsonicTokenLoaded = false;
  let isSavingSubsonicToken = false;

  async function addUser() {
    if (!newUsername) return;
    try {
      const res = await fetch(`${API_BASE}/api/users`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          username: newUsername,
          display_name: newDisplayName,
          password: newUserPassword
        })
      });
      if (res.ok) {
        onMessage(`Gebruiker ${newUsername} toegevoegd!`);
        newUsername = '';
        newDisplayName = '';
        newUserPassword = '';
        fetchUsers();
      } else {
        const data = await res.json();
        onError(data.detail || "Kon gebruiker niet toevoegen.");
      }
    } catch (err) {
      onError("Netwerkfout bij toevoegen gebruiker.");
    }
  }

  async function deleteUser(user) {
    if (!confirm(`Weet je zeker dat je gebruiker ${user.username} wilt verwijderen? Dit verwijdert hem ook uit de Music Server.`)) return;
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
    if (!selectedUser || !updateUserPassword) return;
    try {
      const res = await fetch(`${API_BASE}/api/users/${selectedUser.id}/password`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ password: updateUserPassword })
      });
      if (res.ok) {
        onMessage("Wachtwoord bijgewerkt!");
        updateUserPassword = '';
      } else {
        onError("Kon wachtwoord niet bijwerken.");
      }
    } catch (err) {
      onError("Netwerkfout bij bijwerken wachtwoord.");
    }
  }

  async function syncLMSUsers() {
    try {
      const res = await fetch(`${API_BASE}/api/users/sync/muma-server`, { 
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
      const res = await fetch(`${API_BASE}/api/users/sync/muma-server`, { 
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

  /**
   * Loads the selected user's Subsonic API token. This goes straight to the
   * music server's muma bridge (not the MuMa API) because the token lives in
   * the server's own auth-token store, and it requires Subsonic admin
   * credentials rather than the management API key.
   */
  async function fetchSubsonicToken() {
    subsonicToken = '';
    subsonicTokenLoaded = false;
    if (!selectedUser || !$authParams) return;
    try {
      const res = await fetch(
        `${$mumaApiUrl}/api/admin/subsonic-token?${$authParams}&username=${encodeURIComponent(selectedUser.username)}`
      );
      if (res.ok) {
        const data = await res.json();
        subsonicToken = data.token || '';
        subsonicTokenLoaded = true;
      }
    } catch (err) {
      console.error(err);
    }
  }

  async function saveSubsonicToken(token) {
    if (!selectedUser || !$authParams) return;
    isSavingSubsonicToken = true;
    try {
      const res = await fetch(
        `${$mumaApiUrl}/api/admin/subsonic-token?${$authParams}&username=${encodeURIComponent(selectedUser.username)}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token })
        }
      );
      if (res.ok) {
        const data = await res.json();
        subsonicToken = data.token || '';
        subsonicTokenLoaded = true;
        onMessage(token ? 'Subsonic token opgeslagen.' : 'Subsonic token ingetrokken.');
      } else {
        onError((await res.text()) || 'Kon Subsonic token niet opslaan.');
      }
    } catch (err) {
      onError('Netwerkfout bij opslaan van Subsonic token.');
    } finally {
      isSavingSubsonicToken = false;
    }
  }

  function generateSubsonicToken() {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    const token = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
    saveSubsonicToken(token);
  }

  async function fetchIdentities() {
    if (!selectedUser) return;
    try {
      const res = await fetch(`${API_BASE}/api/users/${selectedUser.id}/identities`, {
        headers: getHeaders()
      });
      if (res.ok) {
        userIdentities = await res.json();
      } else {
        userIdentities = [];
      }
    } catch (err) {
      console.error(err);
    }
  }

  async function updateRole(roleId) {
    if (!selectedUser) return;
    const role = roles.find(r => r.id === roleId)?.name;
    if (!role) return;
    
    try {
      const res = await fetch(`${API_BASE}/api/users/${selectedUser.id}/role`, {
        method: 'PUT',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ role })
      });
      if (res.ok) {
        onMessage("Rol bijgewerkt!");
        fetchUsers();
      } else {
        const data = await res.json();
        onError(data.detail || "Kon rol niet bijwerken.");
      }
    } catch (err) {
      onError("Netwerkfout bij bijwerken rol.");
    }
  }

  async function toggleUserEnabled() {
    if (!selectedUser) return;
    const action = selectedUser.enabled ? 'disable' : 'enable';
    try {
      const res = await fetch(`${API_BASE}/api/users/${selectedUser.id}/${action}`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage(`Gebruiker ${action === 'enable' ? 'ingeschakeld' : 'uitgeschakeld'}!`);
        fetchUsers();
      } else {
        onError(`Kon gebruiker niet ${action === 'enable' ? 'inschakelen' : 'uitschakelen'}.`);
      }
    } catch (err) {
      onError("Netwerkfout.");
    }
  }

  async function revokeSessions() {
    if (!selectedUser) return;
    if (!confirm(`Weet je zeker dat je alle sessies van ${selectedUser.username} wilt intrekken?`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/users/${selectedUser.id}/sessions/revoke`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage("Sessies ingetrokken!");
      } else {
        onError("Kon sessies niet intrekken.");
      }
    } catch (err) {
      onError("Netwerkfout.");
    }
  }

  async function mergeUsers() {
    if (!selectedUser || !mergeSecondaryId) return;
    const secondary = users.find(u => u.id === parseInt(mergeSecondaryId));
    if (!secondary) return;
    if (!confirm(`Weet je zeker dat je ${secondary.username} wilt samenvoegen in ${selectedUser.username}? Alle koppelingen, ratings en luistergeschiedenis van ${secondary.username} worden overgezet en het account ${secondary.username} wordt daarna verwijderd. Dit kan niet ongedaan worden gemaakt.`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/users/${selectedUser.id}/merge`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ secondary_user_id: parseInt(mergeSecondaryId) })
      });
      if (res.ok) {
        onMessage(`${secondary.username} is samengevoegd in ${selectedUser.username}.`);
        mergeSecondaryId = '';
        await fetchUsers();
        fetchIdentities();
      } else {
        const data = await res.json();
        onError(data.detail || "Kon gebruikers niet samenvoegen.");
      }
    } catch (err) {
      onError("Netwerkfout bij samenvoegen.");
    }
  }

  $: if (selectedUser) {
    if (selectedUser.id !== lastSelectedUserId) {
      lastSelectedUserId = selectedUser.id;
      fetchLBAccount();
      fetchIdentities();
      fetchSubsonicToken();
      updateUserPassword = '';
    }
  } else {
    lastSelectedUserId = null;
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
              title="Sync van Music Server"
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
              {#each users as user (user.id)}
                <tr 
                  class="hover:bg-white hover:bg-opacity-5 cursor-pointer transition-colors {selectedUser?.id === user.id ? 'bg-spotify-gray' : ''}"
                  on:click={() => onSelectUser(user)}
                >
                  <td class="p-4">
                    <div class="flex justify-between items-center">
                      <div>
                        <div class="font-bold {selectedUser?.id === user.id ? 'text-spotify-green' : ''}">
                          {user.username}
                          {#if !user.enabled}
                            <span class="ml-2 text-[10px] bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded uppercase tracking-wider font-bold">Uit</span>
                          {/if}
                        </div>
                        <div class="text-xs text-spotify-lightgray flex items-center gap-1.5">
                          {user.display_name || ''} 
                          {#if user.role_name}
                            <span class="inline-flex items-center gap-0.5 text-[10px] bg-white/10 text-white/60 px-1.5 py-0.5 rounded uppercase font-bold">
                              {user.role_name === 'admin' ? 'Admin' : 'User'}
                            </span>
                          {/if}
                        </div>
                      </div>
                      <button 
                        on:click|stopPropagation={() => deleteUser(user)}
                        class="text-spotify-lightgray hover:text-red-500 transition-colors p-2"
                        title="Verwijder gebruiker"
                        disabled={!hasPermission('users.update')}
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
      {#if hasPermission('users.create')}
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
              bind:value={newUserPassword}
              placeholder="Standaard Wachtwoord"
              class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-2 focus:outline-none focus:border-spotify-green transition-colors"
            />
          </div>
          <button type="submit" class="w-full bg-spotify-green text-black font-bold py-2 rounded-full hover:scale-105 transition-transform">
            TOEVOEGEN
          </button>
        </form>
      </div>
      {/if}
    </div>

    <!-- User Detail / External Accounts -->
    <div class="lg:col-span-2">
      {#if selectedUser}
        <div class="space-y-6 animate-in fade-in duration-300">
          <div class="bg-spotify-gray p-8 rounded-xl border border-white border-opacity-5">
            <div class="flex flex-wrap items-center justify-between gap-4 mb-8">
              <div class="flex items-center gap-4">
                {#if selectedUser.avatar_url}
                  <img src={selectedUser.avatar_url} alt="Avatar" class="w-16 h-16 rounded-full" />
                {:else}
                  <div class="w-16 h-16 bg-spotify-green rounded-full flex items-center justify-center text-black text-2xl font-bold">
                    {selectedUser.username.charAt(0).toUpperCase()}
                  </div>
                {/if}
                <div>
                  <h3 class="text-3xl font-extrabold flex items-center gap-2">
                    {selectedUser.username}
                    {#if !selectedUser.enabled}
                      <span class="text-xs bg-red-500/20 text-red-400 px-2 py-1 rounded-full uppercase font-bold tracking-wider">Uitgeschakeld</span>
                    {/if}
                  </h3>
                  <p class="text-spotify-lightgray">{selectedUser.display_name || 'Geen display name'} • {selectedUser.email || 'Geen e-mail'}</p>
                </div>
              </div>

              <div class="flex gap-2">
                {#if hasPermission('users.disable')}
                  <button 
                    on:click={toggleUserEnabled}
                    class="flex items-center gap-2 px-4 py-2 rounded-full text-xs font-bold transition-transform hover:scale-105 {selectedUser.enabled ? 'bg-red-500/10 text-red-500 border border-red-500/20' : 'bg-green-500/10 text-green-500 border border-green-500/20'}"
                  >
                    <Power size={14} /> {selectedUser.enabled ? 'Uitschakelen' : 'Inschakelen'}
                  </button>
                {/if}
                
                {#if hasPermission('users.revoke-sessions') || ($mumaUser && $mumaUser.id === selectedUser.id && hasPermission('sessions.manage-own'))}
                  <button 
                    on:click={revokeSessions}
                    class="flex items-center gap-2 px-4 py-2 rounded-full text-xs font-bold bg-white/5 text-white border border-white/10 transition-transform hover:scale-105"
                  >
                    <LogOut size={14} /> Sessies intrekken
                  </button>
                {/if}
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
              <!-- RBAC Section -->
              <div class="space-y-4">
                <h4 class="text-xl font-bold flex items-center gap-2 text-white">
                  <Shield size={20} class="text-spotify-green" /> Rol & Rechten
                </h4>
                <div class="bg-spotify-dark p-6 rounded-xl border border-spotify-gray space-y-4">
                  <div>
                    <label for="user-role" class="block text-xs font-bold text-spotify-lightgray uppercase mb-1">Gebruikersrol</label>
                    {#if hasPermission('users.assign-role')}
                      <div class="flex gap-2">
                        <select 
                          id="user-role"
                          class="flex-1 bg-spotify-gray bg-opacity-30 border border-spotify-gray rounded-md p-2 focus:outline-none focus:border-spotify-green transition-colors text-sm"
                          value={roles.find(r => r.name === selectedUser.role_name)?.id}
                          on:change={(e) => updateRole(parseInt(e.target.value))}
                        >
                          <option value="" disabled>Selecteer rol</option>
                          {#each roles as role (role.id)}
                            <option value={role.id}>{role.name.charAt(0).toUpperCase() + role.name.slice(1)}</option>
                          {/each}
                        </select>
                      </div>
                    {:else}
                      <div class="p-2 bg-white/5 rounded text-sm text-spotify-lightgray italic">
                        {selectedUser.role_name || 'user'}
                      </div>
                    {/if}
                  </div>
                  
                  {#if selectedUser.role_name === 'admin'}
                    <div class="flex items-center gap-2 text-[10px] text-spotify-green font-bold uppercase">
                      <ShieldCheck size={14} /> Volledige systeemtoegang
                    </div>
                  {:else}
                    <div class="flex items-center gap-2 text-[10px] text-spotify-lightgray font-bold uppercase">
                      <Shield size={14} /> Beperkte gebruikersrechten
                    </div>
                  {/if}
                </div>
              </div>
              <!-- Password Section -->
              <div class="space-y-4">
                <h4 class="text-xl font-bold flex items-center gap-2 text-white">
                  <Key size={20} class="text-spotify-green" /> Beveiliging
                </h4>
                <div class="bg-spotify-dark p-6 rounded-xl border border-spotify-gray space-y-4">
                  <div>
                    <label for="new-password" class="block text-xs font-bold text-spotify-lightgray uppercase mb-1">Nieuw Wachtwoord</label>
                    <input 
                      id="new-password"
                      type="password" 
                      bind:value={updateUserPassword}
                      placeholder="••••••••"
                      class="w-full bg-spotify-gray bg-opacity-30 border border-spotify-gray rounded-md p-2 focus:outline-none focus:border-spotify-green transition-colors"
                    />
                  </div>
                  <button 
                    on:click={updatePassword}
                    disabled={!updateUserPassword}
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
                    <label for="lb-username" class="block text-xs font-bold text-spotify-lightgray uppercase mb-1">LB Username</label>
                    <input 
                      id="lb-username"
                      type="text" 
                      bind:value={lbUsername}
                      placeholder="ListenBrainz User"
                      class="w-full bg-spotify-gray bg-opacity-30 border border-spotify-gray rounded-md p-2 focus:outline-none focus:border-spotify-green transition-colors"
                    />
                  </div>
                  <div>
                    <label for="lb-token" class="block text-xs font-bold text-spotify-lightgray uppercase mb-1">API Token</label>
                    <div class="relative">
                      <Key class="absolute left-2 top-2.5 text-spotify-lightgray" size={16} />
                      <input 
                        id="lb-token"
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

              <!-- Subsonic API token -->
              <div class="space-y-4">
                <h4 class="text-xl font-bold flex items-center gap-2 text-white">
                  <Key size={20} class="text-spotify-green" /> Subsonic API Token
                </h4>
                <div class="bg-spotify-dark p-6 rounded-xl border border-spotify-gray space-y-4">
                  <p class="text-xs text-spotify-lightgray">
                    Sleutel waarmee deze gebruiker externe apps (Ultrasonic, Magna, ...) laat inloggen zonder
                    wachtwoord. Alleen beheerders geven tokens uit.
                  </p>
                  {#if !$authParams}
                    <p class="text-xs text-red-400 italic">
                      Vereist een login met server-inloggegevens op de playerpagina.
                    </p>
                  {:else}
                    <div class="bg-spotify-gray bg-opacity-30 border border-spotify-gray rounded-md p-2 font-mono text-sm break-all min-h-[38px] flex items-center">
                      {#if !subsonicTokenLoaded}
                        <span class="text-spotify-lightgray italic">Laden...</span>
                      {:else if subsonicToken}
                        {subsonicToken}
                      {:else}
                        <span class="text-spotify-lightgray italic">Geen token ingesteld</span>
                      {/if}
                    </div>
                    <div class="flex gap-2">
                      <button
                        on:click={generateSubsonicToken}
                        disabled={isSavingSubsonicToken}
                        class="flex-1 bg-spotify-green text-black text-xs font-bold py-2 rounded-full hover:scale-105 transition-transform disabled:opacity-50"
                      >
                        {subsonicToken ? 'NIEUW TOKEN' : 'TOKEN GENEREREN'}
                      </button>
                      {#if subsonicToken}
                        <button
                          on:click={() => saveSubsonicToken('')}
                          disabled={isSavingSubsonicToken}
                          class="flex-1 bg-red-500/10 text-red-500 text-xs font-bold py-2 rounded-full border border-red-500/20 hover:scale-105 transition-transform disabled:opacity-50"
                        >
                          INTREKKEN
                        </button>
                      {/if}
                    </div>
                  {/if}
                </div>
              </div>

              <!-- Music Server Settings -->
              <div class="space-y-4">
                <h4 class="text-xl font-bold flex items-center gap-2 text-white">
                  <Database size={20} class="text-spotify-green" /> Server Integratie
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

              <!-- Linked Identities -->
              <div class="space-y-4">
                <h4 class="text-xl font-bold flex items-center gap-2 text-white">
                  <Link size={20} class="text-blue-400" /> Gekoppelde accounts
                </h4>
                <div class="bg-spotify-dark p-6 rounded-xl border border-spotify-gray space-y-4">
                  {#if userIdentities.length > 0}
                    <div class="space-y-3">
                      {#each userIdentities as identity (identity.provider + identity.provider_subject)}
                        <div class="flex items-center justify-between p-3 bg-white/5 rounded-lg border border-white/5">
                          <div class="flex items-center gap-3">
                            <div class="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center">
                              {#if identity.provider === 'google'}
                                <svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/><path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
                              {:else}
                                <Users size={16} />
                              {/if}
                            </div>
                            <div>
                              <div class="text-sm font-bold capitalize">{identity.provider}</div>
                              <div class="text-[10px] text-spotify-lightgray">{identity.email_at_provider || identity.provider_subject}</div>
                            </div>
                          </div>
                          <div class="text-right">
                            <div class="text-[10px] text-spotify-lightgray uppercase font-bold">Laatst gebruikt</div>
                            <div class="text-[10px]">{identity.last_used_at ? new Date(identity.last_used_at).toLocaleDateString('nl-NL') : 'Nooit'}</div>
                          </div>
                        </div>
                      {/each}
                    </div>
                  {:else}
                    <p class="text-xs text-spotify-lightgray italic">Geen externe accounts gekoppeld.</p>
                  {/if}
                </div>
              </div>

              <!-- Merge duplicate accounts -->
              {#if hasPermission('users.merge')}
              <div class="space-y-4">
                <h4 class="text-xl font-bold flex items-center gap-2 text-white">
                  <Users size={20} class="text-yellow-400" /> Accounts samenvoegen
                </h4>
                <div class="bg-spotify-dark p-6 rounded-xl border border-spotify-gray space-y-4">
                  <p class="text-xs text-spotify-lightgray">
                    Heeft dezelfde persoon per ongeluk twee accounts (bijv. een lokaal account en een via Google
                    aangevraagd account)? Kies hieronder het account dat verwijderd mag worden; alle koppelingen,
                    ratings en luistergeschiedenis daarvan worden overgezet naar <strong>{selectedUser.username}</strong>.
                  </p>
                  <div>
                    <label for="merge-secondary" class="block text-xs font-bold text-spotify-lightgray uppercase mb-1">Samenvoegen met</label>
                    <select
                      id="merge-secondary"
                      bind:value={mergeSecondaryId}
                      class="w-full bg-spotify-gray bg-opacity-30 border border-spotify-gray rounded-md p-2 focus:outline-none focus:border-spotify-green transition-colors text-sm"
                    >
                      <option value="">Selecteer een ander account</option>
                      {#each users.filter(u => u.id !== selectedUser.id) as user (user.id)}
                        <option value={user.id}>{user.username}{user.display_name ? ` (${user.display_name})` : ''}</option>
                      {/each}
                    </select>
                  </div>
                  <button
                    on:click={mergeUsers}
                    disabled={!mergeSecondaryId}
                    class="w-full bg-yellow-500 text-black text-xs font-bold py-2 rounded-full hover:scale-105 transition-transform disabled:opacity-50"
                  >
                    SAMENVOEGEN EN VERWIJDEREN
                  </button>
                </div>
              </div>
              {/if}
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
