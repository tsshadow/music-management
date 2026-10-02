<script >
  import { t, format } from '../../i18n/index.js';
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
        onMessage($t('management.users.added', { name: newUsername }));
        newUsername = '';
        newDisplayName = '';
        newUserPassword = '';
        fetchUsers();
      } else {
        const data = await res.json();
        onError(data.detail || $t('management.users.addFailed'));
      }
    } catch (err) {
      onError($t('management.users.addNetworkError'));
    }
  }

  async function deleteUser(user) {
    if (!confirm($t('management.users.confirmDelete', { name: user.username }))) return;
    try {
      const res = await fetch(`${API_BASE}/api/users/${user.id}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage($t('management.users.deleted', { name: user.username }));
        if (selectedUser?.id === user.id) onSelectUser(null);
        fetchUsers();
      } else {
        // The server's own reason when it gives one: the last-admin guard (409, bug report 052)
        // and the `users.update` check (403, issue #38) both say why, which "could not delete"
        // does not.
        const data = await res.json().catch(() => ({}));
        onError(typeof data?.detail === 'string' && data.detail ? data.detail : $t('management.users.deleteFailed'));
      }
    } catch (err) {
      onError($t('management.users.deleteNetworkError'));
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
        onMessage($t('management.users.lbLinked'));
        fetchLBAccount();
      } else {
        onError($t('management.users.lbLinkFailed'));
      }
    } catch (err) {
      onError($t('management.users.lbLinkNetworkError'));
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
        onMessage($t('management.users.passwordUpdated'));
        updateUserPassword = '';
      } else {
        onError($t('management.users.passwordUpdateFailed'));
      }
    } catch (err) {
      onError($t('management.users.passwordNetworkError'));
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
        onMessage($t('management.users.syncDone', { count: data.synced }));
        fetchUsers();
      } else {
        onError($t('management.users.syncFailed'));
      }
    } catch (err) {
      onError($t('management.users.syncNetworkError'));
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
        onMessage($t('management.users.dbSyncDone', { count: data.synced }));
        fetchUsers();
      } else {
        onError($t('management.users.syncFailed'));
      }
    } catch (err) {
      onError($t('management.users.syncNetworkError'));
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
        onMessage(token ? $t('management.users.tokenSaved') : $t('management.users.tokenRevoked'));
      } else {
        onError((await res.text()) || $t('management.users.tokenSaveFailed'));
      }
    } catch (err) {
      onError($t('management.users.tokenNetworkError'));
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
        onMessage($t('management.users.roleUpdated'));
        fetchUsers();
      } else {
        const data = await res.json();
        onError(data.detail || $t('management.users.roleUpdateFailed'));
      }
    } catch (err) {
      onError($t('management.users.roleNetworkError'));
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
        onMessage(action === 'enable' ? $t('management.users.enabledMessage') : $t('management.users.disabledMessage'));
        fetchUsers();
      } else {
        onError(action === 'enable' ? $t('management.users.enableFailed') : $t('management.users.disableFailed'));
      }
    } catch (err) {
      onError($t('management.users.networkError'));
    }
  }

  async function revokeSessions() {
    if (!selectedUser) return;
    if (!confirm($t('management.users.confirmRevoke', { name: selectedUser.username }))) return;
    try {
      const res = await fetch(`${API_BASE}/api/users/${selectedUser.id}/sessions/revoke`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage($t('management.users.sessionsRevoked'));
      } else {
        onError($t('management.users.sessionsRevokeFailed'));
      }
    } catch (err) {
      onError($t('management.users.networkError'));
    }
  }

  async function mergeUsers() {
    if (!selectedUser || !mergeSecondaryId) return;
    const secondary = users.find(u => u.id === parseInt(mergeSecondaryId));
    if (!secondary) return;
    if (!confirm($t('management.users.confirmMerge', { from: secondary.username, into: selectedUser.username }))) return;
    try {
      const res = await fetch(`${API_BASE}/api/users/${selectedUser.id}/merge`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ secondary_user_id: parseInt(mergeSecondaryId) })
      });
      if (res.ok) {
        onMessage($t('management.users.merged', { from: secondary.username, into: selectedUser.username }));
        mergeSecondaryId = '';
        await fetchUsers();
        fetchIdentities();
      } else {
        const data = await res.json();
        onError(data.detail || $t('management.users.mergeFailed'));
      }
    } catch (err) {
      onError($t('management.users.mergeNetworkError'));
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
    <p class="text-muma-spotify-text">{$t('management.users.subtitle')}</p>
  </header>

  <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
    <!-- User List -->
    <div class="lg:col-span-1 space-y-6">
      <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
        <h3 class="p-6 text-xl font-bold bg-black/20 flex justify-between items-center">
          {$t('management.tabs.users')}
          <div class="flex gap-2">
            <button 
              on:click={syncLMSUsers} 
              title={$t('management.users.syncFromServer')}
              class="text-muma-spotify-text hover:text-brand transition-colors"
            >
              <RefreshCw size={16} />
            </button>
            <button 
              on:click={fetchUsers} 
              title={$t('common.refresh')}
              class="text-muma-spotify-text hover:text-white transition-colors"
            >
              <RefreshCw size={16} class="rotate-90" />
            </button>
          </div>
        </h3>
        <div class="max-h-[400px] overflow-y-auto">
          <table class="w-full text-left text-sm">
            <tbody class="divide-y divide-muma-spotify-panel/30">
              {#each users as user (user.id)}
                <tr 
                  class="hover:bg-white/5 cursor-pointer transition-colors {selectedUser?.id === user.id ? 'bg-muma-spotify-panel' : ''}"
                  on:click={() => onSelectUser(user)}
                >
                  <td class="p-4">
                    <div class="flex justify-between items-center">
                      <div>
                        <div class="font-bold {selectedUser?.id === user.id ? 'text-brand' : ''}">
                          {user.username}
                          {#if !user.enabled}
                            <span class="ml-2 text-[10px] bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded uppercase tracking-wider font-bold">{$t('management.users.off')}</span>
                          {/if}
                        </div>
                        <div class="text-xs text-muma-spotify-text flex items-center gap-1.5">
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
                        class="text-muma-spotify-text hover:text-red-500 transition-colors p-2"
                        title={$t('management.users.deleteUser')}
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
      <div class="bg-muma-spotify-panel p-6 rounded-xl border border-white/5">
        <h3 class="text-xl font-bold mb-4 flex items-center gap-2"><Plus size={20} class="text-brand" /> {$t('management.users.addUser')}</h3>
        <form on:submit|preventDefault={addUser} class="space-y-4">
          <div>
            <input 
              type="text" 
              bind:value={newUsername}
              placeholder={$t('login.username')}
              class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-2 focus:outline-none focus:border-brand transition-colors"
            />
          </div>
          <div>
            <input 
              type="text" 
              bind:value={newDisplayName}
              placeholder={$t('management.users.displayNamePlaceholder')}
              class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-2 focus:outline-none focus:border-brand transition-colors"
            />
          </div>
          <div>
            <input 
              type="password" 
              bind:value={newUserPassword}
              placeholder={$t('management.users.defaultPasswordPlaceholder')}
              class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-2 focus:outline-none focus:border-brand transition-colors"
            />
          </div>
          <button type="submit" class="w-full bg-brand text-black font-bold py-2 rounded-full hover:scale-105 transition-transform">
            {$t('management.downloaders.add')}
          </button>
        </form>
      </div>
      {/if}
    </div>

    <!-- User Detail / External Accounts -->
    <div class="lg:col-span-2">
      {#if selectedUser}
        <div class="space-y-6 animate-in fade-in duration-300">
          <div class="bg-muma-spotify-panel p-8 rounded-xl border border-white/5">
            <div class="flex flex-wrap items-center justify-between gap-4 mb-8">
              <div class="flex items-center gap-4">
                {#if selectedUser.avatar_url}
                  <img src={selectedUser.avatar_url} alt={$t('login.avatar')} class="w-16 h-16 rounded-full" />
                {:else}
                  <div class="w-16 h-16 bg-brand rounded-full flex items-center justify-center text-black text-2xl font-bold">
                    {selectedUser.username.charAt(0).toUpperCase()}
                  </div>
                {/if}
                <div>
                  <h3 class="text-3xl font-extrabold flex items-center gap-2">
                    {selectedUser.username}
                    {#if !selectedUser.enabled}
                      <span class="text-xs bg-red-500/20 text-red-400 px-2 py-1 rounded-full uppercase font-bold tracking-wider">{$t('management.users.disabled')}</span>
                    {/if}
                  </h3>
                  <p class="text-muma-spotify-text">{selectedUser.display_name || $t('management.users.noDisplayName')} • {selectedUser.email || $t('management.users.noEmail')}</p>
                </div>
              </div>

              <div class="flex gap-2">
                {#if hasPermission('users.disable')}
                  <button 
                    on:click={toggleUserEnabled}
                    class="flex items-center gap-2 px-4 py-2 rounded-full text-xs font-bold transition-transform hover:scale-105 {selectedUser.enabled ? 'bg-red-500/10 text-red-500 border border-red-500/20' : 'bg-green-500/10 text-green-500 border border-green-500/20'}"
                  >
                    <Power size={14} /> {selectedUser.enabled ? $t('management.users.disable') : $t('management.users.enable')}
                  </button>
                {/if}
                
                {#if hasPermission('users.revoke-sessions') || ($mumaUser && $mumaUser.id === selectedUser.id && hasPermission('sessions.manage-own'))}
                  <button 
                    on:click={revokeSessions}
                    class="flex items-center gap-2 px-4 py-2 rounded-full text-xs font-bold bg-white/5 text-white border border-white/10 transition-transform hover:scale-105"
                  >
                    <LogOut size={14} /> {$t('management.users.revokeSessions')}
                  </button>
                {/if}
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
              <!-- RBAC Section -->
              <div class="space-y-4">
                <h4 class="text-xl font-bold flex items-center gap-2 text-white">
                  <Shield size={20} class="text-brand" /> {$t('management.users.roleAndRights')}
                </h4>
                <div class="bg-muma-spotify-dark p-6 rounded-xl border border-muma-spotify-panel space-y-4">
                  <div>
                    <label for="user-role" class="block text-xs font-bold text-muma-spotify-text uppercase mb-1">{$t('management.users.role')}</label>
                    {#if hasPermission('users.assign-role')}
                      <div class="flex gap-2">
                        <select 
                          id="user-role"
                          class="flex-1 bg-muma-spotify-panel/30 border border-muma-spotify-panel rounded-md p-2 focus:outline-none focus:border-brand transition-colors text-sm"
                          value={roles.find(r => r.name === selectedUser.role_name)?.id}
                          on:change={(e) => updateRole(parseInt(e.target.value))}
                        >
                          <option value="" disabled>{$t('management.users.selectRole')}</option>
                          {#each roles as role (role.id)}
                            <option value={role.id}>{role.name.charAt(0).toUpperCase() + role.name.slice(1)}</option>
                          {/each}
                        </select>
                      </div>
                    {:else}
                      <div class="p-2 bg-white/5 rounded text-sm text-muma-spotify-text italic">
                        {selectedUser.role_name || 'user'}
                      </div>
                    {/if}
                  </div>
                  
                  {#if selectedUser.role_name === 'admin'}
                    <div class="flex items-center gap-2 text-[10px] text-brand font-bold uppercase">
                      <ShieldCheck size={14} /> {$t('management.users.fullAccess')}
                    </div>
                  {:else}
                    <div class="flex items-center gap-2 text-[10px] text-muma-spotify-text font-bold uppercase">
                      <Shield size={14} /> {$t('management.users.limitedAccess')}
                    </div>
                  {/if}
                </div>
              </div>
              <!-- Password Section -->
              <div class="space-y-4">
                <h4 class="text-xl font-bold flex items-center gap-2 text-white">
                  <Key size={20} class="text-brand" /> {$t('settings.advanced.security')}
                </h4>
                <div class="bg-muma-spotify-dark p-6 rounded-xl border border-muma-spotify-panel space-y-4">
                  <div>
                    <label for="new-password" class="block text-xs font-bold text-muma-spotify-text uppercase mb-1">{$t('settings.advanced.newPassword')}</label>
                    <input 
                      id="new-password"
                      type="password" 
                      bind:value={updateUserPassword}
                      placeholder="••••••••"
                      class="w-full bg-muma-spotify-panel/30 border border-muma-spotify-panel rounded-md p-2 focus:outline-none focus:border-brand transition-colors"
                    />
                  </div>
                  <button 
                    on:click={updatePassword}
                    disabled={!updateUserPassword}
                    class="w-full bg-brand text-black text-xs font-bold py-2 rounded-full hover:scale-105 transition-transform disabled:opacity-50"
                  >
                    {$t('management.users.savePassword')}
                  </button>
                </div>
              </div>

              <!-- ListenBrainz Section -->
              <div class="space-y-4">
                <h4 class="text-xl font-bold flex items-center gap-2 text-white">
                  <Radio size={20} class="text-[#EB743B]" /> {$t('management.users.listenBrainz')}
                </h4>
                <div class="bg-muma-spotify-dark p-6 rounded-xl border border-muma-spotify-panel space-y-4">
                  <div>
                    <label for="lb-username" class="block text-xs font-bold text-muma-spotify-text uppercase mb-1">{$t('management.users.lbUsername')}</label>
                    <input 
                      id="lb-username"
                      type="text" 
                      bind:value={lbUsername}
                      placeholder={$t('management.users.lbUserPlaceholder')}
                      class="w-full bg-muma-spotify-panel/30 border border-muma-spotify-panel rounded-md p-2 focus:outline-none focus:border-brand transition-colors"
                    />
                  </div>
                  <div>
                    <label for="lb-token" class="block text-xs font-bold text-muma-spotify-text uppercase mb-1">{$t('management.users.apiToken')}</label>
                    <div class="relative">
                      <Key class="absolute left-2 top-2.5 text-muma-spotify-text" size={16} />
                      <input 
                        id="lb-token"
                        type="password" 
                        bind:value={lbToken}
                        placeholder={$t('management.users.tokenPlaceholder')}
                        class="w-full bg-muma-spotify-panel/30 border border-muma-spotify-panel rounded-md p-2 pl-9 focus:outline-none focus:border-brand transition-colors font-mono text-sm"
                      />
                    </div>
                  </div>
                  <div class="flex gap-2">
                    <button 
                      on:click={() => navigateToScrobbleImport(selectedUser.username, lbUsername)}
                      class="flex-1 bg-white text-black text-xs font-bold py-2 rounded-full hover:scale-105 transition-transform"
                    >
                      {$t('management.scrobble.startImport')}
                    </button>
                    <button 
                      on:click={updateLBAccount}
                      class="flex-1 bg-brand text-black text-xs font-bold py-2 rounded-full hover:scale-105 transition-transform"
                    >
                      {$t('management.users.saveUpper')}
                    </button>
                  </div>
                </div>
              </div>

              <!-- Subsonic API token -->
              <div class="space-y-4">
                <h4 class="text-xl font-bold flex items-center gap-2 text-white">
                  <Key size={20} class="text-brand" /> {$t('management.users.subsonicToken')}
                </h4>
                <div class="bg-muma-spotify-dark p-6 rounded-xl border border-muma-spotify-panel space-y-4">
                  <p class="text-xs text-muma-spotify-text">
                    {$t('management.users.subsonicTokenHelp')}
                  </p>
                  {#if !$authParams}
                    <p class="text-xs text-red-400 italic">
                      {$t('management.users.needsServerLogin')}
                    </p>
                  {:else}
                    <div class="bg-muma-spotify-panel/30 border border-muma-spotify-panel rounded-md p-2 font-mono text-sm break-all min-h-[38px] flex items-center">
                      {#if !subsonicTokenLoaded}
                        <span class="text-muma-spotify-text italic">{$t('common.loading')}</span>
                      {:else if subsonicToken}
                        {subsonicToken}
                      {:else}
                        <span class="text-muma-spotify-text italic">{$t('management.users.noToken')}</span>
                      {/if}
                    </div>
                    <div class="flex gap-2">
                      <button
                        on:click={generateSubsonicToken}
                        disabled={isSavingSubsonicToken}
                        class="flex-1 bg-brand text-black text-xs font-bold py-2 rounded-full hover:scale-105 transition-transform disabled:opacity-50"
                      >
                        {subsonicToken ? $t('management.users.newToken') : $t('management.users.generateToken')}
                      </button>
                      {#if subsonicToken}
                        <button
                          on:click={() => saveSubsonicToken('')}
                          disabled={isSavingSubsonicToken}
                          class="flex-1 bg-red-500/10 text-red-500 text-xs font-bold py-2 rounded-full border border-red-500/20 hover:scale-105 transition-transform disabled:opacity-50"
                        >
                          {$t('management.users.revokeToken')}
                        </button>
                      {/if}
                    </div>
                  {/if}
                </div>
              </div>

              <!-- Music Server Settings -->
              <div class="space-y-4">
                <h4 class="text-xl font-bold flex items-center gap-2 text-white">
                  <Database size={20} class="text-brand" /> {$t('management.users.serverIntegration')}
                </h4>
                <div class="bg-muma-spotify-dark p-6 rounded-xl border border-muma-spotify-panel space-y-4">
                  <p class="text-xs text-muma-spotify-text">{$t('management.users.serverIntegrationHelp')}</p>
                  <div class="flex flex-col gap-2">
                    <button 
                      on:click={syncLMSUsers}
                      class="w-full bg-white text-black text-xs font-bold py-2 rounded-full hover:scale-105 transition-transform flex items-center justify-center gap-2"
                    >
                      <RefreshCw size={14} /> {$t('management.users.syncViaApi')}
                    </button>
                    <button 
                      on:click={syncLMSDbUsers}
                      class="w-full bg-brand text-black text-xs font-bold py-2 rounded-full hover:scale-105 transition-transform flex items-center justify-center gap-2"
                    >
                      <Database size={14} /> {$t('management.users.syncViaDatabase')}
                    </button>
                  </div>
                </div>
              </div>

              <!-- Linked Identities -->
              <div class="space-y-4">
                <h4 class="text-xl font-bold flex items-center gap-2 text-white">
                  <Link size={20} class="text-blue-400" /> {$t('management.users.linkedAccounts')}
                </h4>
                <div class="bg-muma-spotify-dark p-6 rounded-xl border border-muma-spotify-panel space-y-4">
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
                              <div class="text-[10px] text-muma-spotify-text">{identity.email_at_provider || identity.provider_subject}</div>
                            </div>
                          </div>
                          <div class="text-right">
                            <div class="text-[10px] text-muma-spotify-text uppercase font-bold">{$t('management.users.lastUsed')}</div>
                            <div class="text-[10px]">{identity.last_used_at ? $format.date(identity.last_used_at) : $t('management.users.never')}</div>
                          </div>
                        </div>
                      {/each}
                    </div>
                  {:else}
                    <p class="text-xs text-muma-spotify-text italic">{$t('management.users.noLinkedAccounts')}</p>
                  {/if}
                </div>
              </div>

              <!-- Merge duplicate accounts -->
              {#if hasPermission('users.merge')}
              <div class="space-y-4">
                <h4 class="text-xl font-bold flex items-center gap-2 text-white">
                  <Users size={20} class="text-yellow-400" /> {$t('management.users.mergeAccounts')}
                </h4>
                <div class="bg-muma-spotify-dark p-6 rounded-xl border border-muma-spotify-panel space-y-4">
                  <p class="text-xs text-muma-spotify-text">
                    {$t('management.users.mergeHelp')} <strong>{selectedUser.username}</strong>.
                  </p>
                  <div>
                    <label for="merge-secondary" class="block text-xs font-bold text-muma-spotify-text uppercase mb-1">{$t('management.users.mergeWith')}</label>
                    <select
                      id="merge-secondary"
                      bind:value={mergeSecondaryId}
                      class="w-full bg-muma-spotify-panel/30 border border-muma-spotify-panel rounded-md p-2 focus:outline-none focus:border-brand transition-colors text-sm"
                    >
                      <option value="">{$t('management.users.selectOtherAccount')}</option>
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
                    {$t('management.users.mergeAndDelete')}
                  </button>
                </div>
              </div>
              {/if}
            </div>
          </div>
        </div>
      {:else}
        <div class="h-full flex items-center justify-center bg-muma-spotify-panel/20 rounded-xl border border-dashed border-muma-spotify-panel p-12 text-center text-muma-spotify-text">
          <div>
            <Users size={48} class="mx-auto mb-4 opacity-20" />
            <p class="text-xl font-bold">{$t('management.users.selectUser')}</p>
            <p>{$t('management.users.selectUserHelp')}</p>
          </div>
        </div>
      {/if}
    </div>
  </div>
</section>
