<script>
  import { authParams } from '../store.js';

  const { user = null, onclose, onsave } = $props();

  // svelte-ignore state_referenced_locally
  let username = $state(user ? user.username : '');
  let password = $state('');
  // svelte-ignore state_referenced_locally
  let isAdmin = $state(user ? user.adminRole : false);
  // svelte-ignore state_referenced_locally
  let scrobblingEnabled = $state(user ? user.scrobblingEnabled : true);
  const isEditing = $derived(!!user);
  let error = $state('');
  let isSaving = $state(false);

  async function handleSubmit(e) {
    e.preventDefault();
    isSaving = true;
    error = '';

    const endpoint = isEditing ? '/rest/updateUser' : '/rest/createUser';
    // eslint-disable-next-line svelte/prefer-svelte-reactivity
    const params = new URLSearchParams($authParams);
    params.append('username', username);
    if (password) params.append('password', password);
    params.append('adminRole', String(isAdmin));
    params.append('scrobblingEnabled', String(scrobblingEnabled));

    try {
      const response = await fetch(`${endpoint}?${params.toString()}`);
      const data = await response.json();
      const res = data['subsonic-response'];

      if (res.status === 'ok') {
        onsave();
      } else {
        error = res.error?.message || 'Er is een fout opgetreden';
      }
    } catch {
      error = 'Netwerkfout';
    } finally {
      isSaving = false;
    }
  }

  async function handleDelete() {
    if (!confirm(`Weet je zeker dat je gebruiker ${username} wilt verwijderen?`)) return;
    
    isSaving = true;
    // eslint-disable-next-line svelte/prefer-svelte-reactivity
    const params = new URLSearchParams($authParams);
    params.append('username', username);

    try {
      const response = await fetch(`/rest/deleteUser?${params.toString()}`);
      const data = await response.json();
      if (data['subsonic-response'].status === 'ok') {
        onsave();
      } else {
        error = data['subsonic-response'].error?.message || 'Kon gebruiker niet verwijderen';
      }
    } catch {
      error = 'Netwerkfout';
    } finally {
      isSaving = false;
    }
  }
</script>

<div class="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
  <div class="bg-[#282828] p-8 rounded-lg w-full max-w-md shadow-2xl">
    <div class="flex justify-between items-center mb-6">
      <h3 class="text-2xl font-bold text-white">{isEditing ? 'Edit User' : 'Create New User'}</h3>
      <button onclick={onclose} class="text-[#b3b3b3] hover:text-white bg-transparent border-none cursor-pointer" aria-label="Close">
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
      </button>
    </div>

    <form onsubmit={handleSubmit} class="space-y-4">
      <div>
        <label for="username" class="block text-xs font-bold uppercase mb-2 text-[#b3b3b3]">Username</label>
        <input
          id="username"
          type="text"
          bind:value={username}
          disabled={isEditing}
          class="w-full bg-[#3e3e3e] border-none rounded p-3 text-white focus:outline-none focus:ring-2 focus:ring-white disabled:opacity-50"
          required
        />
      </div>

      <div>
        <label for="password" class="block text-xs font-bold uppercase mb-2 text-[#b3b3b3]">
          {isEditing ? 'New Password (leave empty to keep current)' : 'Password'}
        </label>
        <input
          id="password"
          type="password"
          bind:value={password}
          class="w-full bg-[#3e3e3e] border-none rounded p-3 text-white focus:outline-none focus:ring-2 focus:ring-white"
          required={!isEditing}
        />
      </div>

      <div class="flex items-center gap-3 py-2">
        <input type="checkbox" id="isAdmin" bind:checked={isAdmin} class="w-5 h-5 accent-[#1db954]" />
        <label for="isAdmin" class="text-sm font-medium text-white cursor-pointer select-none">Administrator role</label>
      </div>

      <div class="flex items-center gap-3 py-2">
        <input type="checkbox" id="scrobbling" bind:checked={scrobblingEnabled} class="w-5 h-5 accent-[#1db954]" />
        <label for="scrobbling" class="text-sm font-medium text-white cursor-pointer select-none">Scrobbling enabled</label>
      </div>

      {#if error}
        <p class="text-red-500 text-sm mt-2">{error}</p>
      {/if}

      <div class="flex gap-4 mt-8">
        <button
          type="submit"
          disabled={isSaving}
          class="flex-1 bg-[#1db954] text-black font-bold py-3 rounded-full hover:scale-105 transition-transform disabled:opacity-50 cursor-pointer border-none"
        >
          {isSaving ? 'Saving...' : 'Save'}
        </button>
        <button
          type="button"
          onclick={onclose}
          class="flex-1 bg-transparent border border-[#727272] text-white font-bold py-3 rounded-full hover:border-white transition-colors cursor-pointer"
        >
          Cancel
        </button>
      </div>

      {#if isEditing}
        <button
          type="button"
          onclick={handleDelete}
          disabled={isSaving}
          class="w-full text-red-500 text-sm font-bold mt-4 hover:underline cursor-pointer bg-transparent border-none"
        >
          Delete User
        </button>
      {/if}
    </form>
  </div>
</div>