<script>
  import { onMount } from 'svelte';
  import { authParams } from '../store.js';

  let users = [];
  let isLoading = true;

  async function loadUsers() {
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

  function getInitials(name) {
    return name ? name.charAt(0).toUpperCase() : '?';
  }

  function getAvatarColor(name) {
    const colors = ['bg-blue-500', 'bg-purple-500', 'bg-green-500', 'bg-red-500', 'bg-yellow-500', 'bg-indigo-500'];
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
      hash = name.charCodeAt(i) + ((hash << 5) - hash);
    }
    return colors[Math.abs(hash) % colors.length];
  }
</script>

<section>
  <h3 class="text-2xl font-bold mb-6">Users</h3>
  
  {#if isLoading}
    <div class="text-[#b3b3b3]">Laden...</div>
  {:else}
    <div class="grid gap-4">
      {#each users as user (user.username)}
        <div class="bg-[#181818] p-4 rounded-lg flex justify-between items-center hover:bg-[#282828] transition-colors">
            <div class="flex items-center gap-4">
                <div class="w-10 h-10 {getAvatarColor(user.username)} rounded-full flex items-center justify-center font-bold text-white">
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
            <button class="text-[#b3b3b3] hover:text-white cursor-pointer border-none bg-transparent font-medium">Manage</button>
        </div>
      {/each}
    </div>

    <button class="mt-8 bg-white text-black px-8 py-3 rounded-full font-bold hover:scale-105 transition-transform cursor-pointer border-none">
        Create New User
    </button>
  {/if}
</section>
