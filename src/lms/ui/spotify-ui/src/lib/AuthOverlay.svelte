<script>
  import { credentials } from './store.js';

  let username = '';
  let password = '';
  let error = '';
  let isLoading = false;

  async function verifyLogin() {
    error = '';
    isLoading = true;
    
    const params = `u=${encodeURIComponent(username)}&p=${encodeURIComponent(password)}&v=1.12.0&c=spotify-ui&f=json`;
    try {
      const response = await fetch(`${window.location.origin}/rest/ping?${params}`);
      const data = await response.json();
      
      if (data['subsonic-response'] && data['subsonic-response'].status === 'ok') {
        save();
      } else {
        const errorMsg = data['subsonic-response']?.error?.message || 'Ongeldige gebruikersnaam of wachtwoord';
        error = `Fout: ${errorMsg}`;
      }
    } catch (e) {
      error = 'Kon geen verbinding maken met de server';
    } finally {
      isLoading = false;
    }
  }

  function save() {
    credentials.update(c => ({ ...c, username, password }));
  }

  // Load from store on init
  import { onMount } from 'svelte';
  onMount(() => {
    if ($credentials.username) {
        username = $credentials.username;
        password = $credentials.password;
    }
  });
</script>

{#if !$credentials.username}
<div class="fixed inset-0 w-screen h-screen bg-black/80 flex justify-center items-center z-[1000]">
  <div class="bg-[#282828] p-8 rounded-lg w-[400px] flex flex-col gap-5">
    <h2 class="m-0">LMS Inloggen</h2>
    <p class="text-sm">Voer je Subsonic inloggegevens in om muziek te kunnen streamen.</p>
    
    {#if error}
      <div class="bg-[#e91429] text-white p-2.5 rounded text-sm">{error}</div>
    {/if}

    <div class="flex flex-col gap-2">
      <label class="text-[12px] font-bold text-[#b3b3b3] uppercase">Gebruikersnaam</label>
      <input type="text" bind:value={username} placeholder="Username" class="bg-[#3e3e3e] border border-transparent rounded p-3 text-white text-sm focus:outline-none focus:border-spotify-green disabled:opacity-50 disabled:cursor-not-allowed" disabled={isLoading} />
    </div>
    <div class="flex flex-col gap-2">
      <label class="text-[12px] font-bold text-[#b3b3b3] uppercase">Wachtwoord</label>
      <input type="password" bind:value={password} placeholder="Password" class="bg-[#3e3e3e] border border-transparent rounded p-3 text-white text-sm focus:outline-none focus:border-spotify-green disabled:opacity-50 disabled:cursor-not-allowed" disabled={isLoading} on:keydown={(e) => e.key === 'Enter' && verifyLogin()} />
    </div>
    <button class="bg-spotify-green text-black border-none rounded-[500px] p-3.5 text-base font-bold cursor-pointer transition-transform hover:scale-[1.04] disabled:bg-spotify-green/50 disabled:cursor-not-allowed disabled:transform-none" on:click={verifyLogin} disabled={isLoading}>
      {isLoading ? 'Verificeren...' : 'Verbinden'}
    </button>
  </div>
</div>
{/if}

<style>
</style>
