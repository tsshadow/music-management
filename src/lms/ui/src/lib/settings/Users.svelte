<script>
  import { onMount } from 'svelte';
  import { authParams } from '../store.js';
  import UserEditor from './UserEditor.svelte';

  let users = $state([]);
  let isLoading = $state(true);
  let editingUser = $state(null);
  let showCreateModal = $state(false);

  /**
   * Fetches the list of all users from the server.
   */
  async function loadUsers() {
    isLoading = true;
    try {
      const response = await fetch(`/rest/getUsers?${$authParams}`);
      const data = await response.json();
      const res = data['subsonic-response'];
      if (res && res.users) {
        users = Array.isArray(res.users.user) ? res.users.user : [res.users.user];
      }
    } catch (e) {
      console.error(e);
    } finally {
      isLoading = false;
    }
  }

  onMount(loadUsers);

  /**
   * Returns the first character of a username as initials.
   *
   * @param {string} name - The username.
   * @returns {string} The first character capitalized.
   */
  function getInitials(name) {
    return name ? name.charAt(0).toUpperCase() : '?';
  }

  /**
   * Generates a consistent background color for a user's avatar based on their name.
   *
   * @param {string} name - The username.
   * @returns {string} Tailwind CSS class for background color.
   */
  function getAvatarColor(name) {
    const colors = ['bg-blue-500', 'bg-purple-500', 'bg-green-500', 'bg-red-500', 'bg-yellow-500', 'bg-indigo-500'];
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
      hash = name.charCodeAt(i) + ((hash << 5) - hash);
    }
    return colors[Math.abs(hash) % colors.length];
  }

  /**
   * Opens the user editor for a specific user.
   *
   * @param {Object} user - The user object to edit.
   */
  function handleEdit(user) {
    editingUser = user;
  }

  /**
   * Opens the user editor to create a new user.
   */
  function handleCreate() {
    showCreateModal = true;
  }

  /**
   * Closes the editor and refreshes the user list after a successful save.
   */
  function handleSave() {
    editingUser = null;
    showCreateModal = false;
    loadUsers();
  }

  /**
   * Synchronizes users from the external MusicManagement service.
   */
  async function syncUsers() {
    try {
      await fetch(`/rest/syncUsers?${$authParams}`);
      loadUsers();
    } catch (e) {
      console.error('Failed to sync users:', e);
    }
  }
</script>

<section>
  <div class="flex justify-between items-center mb-6">
    <h3 class="text-2xl font-bold text-white">Users</h3>
    <button
        onclick={syncUsers}
        class="bg-[#1db954] hover:bg-[#1ed760] text-black px-4 py-2 rounded-full text-sm font-bold transition-colors cursor-pointer border-none shadow-md hover:scale-105 active:scale-95"
    >
        Synch
    </button>
  </div>

  {#if isLoading && users.length === 0}
    <div class="text-[#b3b3b3]">Laden...</div>
  {:else}
    <div class="grid gap-4">
      {#each users as user (user.username)}
        <div class="bg-[#181818] p-4 rounded-lg flex justify-between items-center hover:bg-[#282828] transition-colors group">
            <div class="flex items-center gap-4">
                <div class="w-10 h-10 {getAvatarColor(user.username)} rounded-full flex items-center justify-center font-bold text-white shadow-md">
                    {getInitials(user.username)}
                </div>
                <div>
                    <p class="font-bold text-white">{user.username}</p>
                    <p class="text-xs text-[#b3b3b3]">
                        {user.adminRole ? 'Administrator' : 'User'}
                        {#if user.scrobblingEnabled} • Scrobbling{/if}
                    </p>
                </div>
            </div>
            <button
                onclick={() => handleEdit(user)}
                class="text-[#b3b3b3] hover:text-white cursor-pointer border-none bg-transparent font-medium py-2 px-4 rounded-full hover:bg-[#333] transition-all"
            >
                Manage
            </button>
        </div>
      {/each}
    </div>

    <button
        onclick={handleCreate}
        class="mt-8 bg-white text-black px-8 py-3 rounded-full font-bold hover:scale-105 transition-transform cursor-pointer border-none shadow-lg active:scale-95"
    >
        Create New User
    </button>
  {/if}

  {#if editingUser}
    <UserEditor
        user={editingUser}
        onclose={() => editingUser = null}
        onsave={handleSave}
    />
  {/if}

  {#if showCreateModal}
    <UserEditor
        onclose={() => showCreateModal = false}
        onsave={handleSave}
    />
  {/if}
</section>
