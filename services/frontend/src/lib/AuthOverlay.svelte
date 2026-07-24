<script>
  import { credentials, mumaApiUrl } from './store.js';

  let username = '';
  let password = '';
  let error = '';
  let isLoading = false;
  let setupRequired = false;

  const SUBSONIC_BASE = import.meta.env.VITE_SUBSONIC_URL || (import.meta.env.DEV ? '' : window.location.origin);

  /**
   * Verifies the provided credentials by pinging the Subsonic API.
   */
  async function verifyLogin() {
    error = '';
    isLoading = true;

    const params = `u=${encodeURIComponent(username)}&p=${encodeURIComponent(password)}&v=1.12.0&c=spotify&f=json`;
    try {
      const response = await fetch(`${SUBSONIC_BASE}/rest/ping?${params}`);
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

  /**
   * Performs the initial administrative setup.
   */
  async function performSetup() {
    error = '';
    isLoading = true;

    try {
      const response = await fetch(`${$mumaApiUrl}/api/auth/setup`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          username,
          password,
          display_name: username
        })
      });

      if (response.ok) {
        setupRequired = false;
        // Give the server a moment to sync the new user
        error = '';
        setTimeout(verifyLogin, 1000);
      } else {
        const data = await response.json();
        error = data.detail || 'Setup mislukt';
      }
    } catch (e) {
      error = 'Kon geen verbinding maken met de management API';
    } finally {
      isLoading = false;
    }
  }

  /**
   * Saves the verified credentials to the global store.
   */
  function save() {
    credentials.update(c => ({ ...c, username, password }));
  }

  // Load from store on init
  import { onMount } from 'svelte';
  onMount(async () => {
    if ($credentials.username) {
        username = $credentials.username;
        password = $credentials.password;
    }

    try {
      const res = await fetch(`${$mumaApiUrl}/api/auth/setup-status`);
      if (res.ok) {
        const data = await res.json();
        setupRequired = data.setup_required;
      }
    } catch (e) {
      console.warn('Could not check setup status', e);
    }
  });
</script>

{#if !$credentials.username}
<div class="fixed inset-0 w-screen h-screen bg-black/80 flex justify-center items-center z-[1000]">
  <div class="bg-[#282828] p-8 rounded-lg w-[400px] flex flex-col gap-5">
    <h2 class="m-0">{setupRequired ? 'MuMa Systeem Setup' : 'MuMa Spotify Inloggen'}</h2>
    <p class="text-sm">
      {setupRequired 
        ? 'Er zijn nog geen gebruikers gevonden. Maak de eerste beheerder aan om te beginnen.' 
        : 'Voer je Subsonic inloggegevens in om muziek te kunnen streamen.'}
    </p>

    {#if error}
      <div class="bg-[#e91429] text-white p-2.5 rounded text-sm">{error}</div>
    {/if}

    <div class="flex flex-col gap-2">
      <label for="username" class="text-[12px] font-bold text-[#b3b3b3] uppercase">Gebruikersnaam</label>
      <input id="username" type="text" bind:value={username} placeholder="Username" class="bg-[#3e3e3e] border border-transparent rounded p-3 text-white text-sm focus:outline-none focus:border-brand disabled:opacity-50 disabled:cursor-not-allowed" disabled={isLoading} />
    </div>
    <div class="flex flex-col gap-2">
      <label for="password" class="text-[12px] font-bold text-[#b3b3b3] uppercase">Wachtwoord</label>
      <input id="password" type="password" bind:value={password} placeholder="Password" class="bg-[#3e3e3e] border border-transparent rounded p-3 text-white text-sm focus:outline-none focus:border-brand disabled:opacity-50 disabled:cursor-not-allowed" disabled={isLoading} on:keydown={(e) => e.key === 'Enter' && (setupRequired ? performSetup() : verifyLogin())} />
    </div>
    <button class="bg-brand text-black border-none rounded-[500px] p-3.5 text-base font-bold cursor-pointer transition-transform hover:scale-[1.04] disabled:bg-brand/50 disabled:cursor-not-allowed disabled:transform-none" on:click={setupRequired ? performSetup : verifyLogin} disabled={isLoading}>
      {isLoading ? (setupRequired ? 'Bezig met instellen...' : 'Verificeren...') : (setupRequired ? 'Account Aanmaken' : 'Verbinden')}
    </button>
  </div>
</div>
{/if}

<style>
</style>
