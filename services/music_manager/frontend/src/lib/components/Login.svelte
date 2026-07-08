<script lang="ts">
  import { Music } from 'lucide-svelte';
  
  export let API_BASE: string;
  export let onLoginSuccess: (apiKey: string) => void;

  let username = '';
  let password = '';
  let loginError = '';
  let isLoggingIn = false;

  async function login() {
    isLoggingIn = true;
    loginError = '';
    try {
      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      if (res.ok) {
        const data = await res.json();
        onLoginSuccess(data.api_key);
      } else {
        loginError = "Ongeldige gebruikersnaam of wachtwoord.";
      }
    } catch (err) {
      loginError = "Kon geen verbinding maken met de server.";
    } finally {
      isLoggingIn = false;
    }
  }
</script>

<div class="min-h-screen bg-black flex items-center justify-center p-4">
  <div class="bg-spotify-gray w-full max-w-md p-10 rounded-2xl shadow-2xl border border-white border-opacity-5 animate-in fade-in zoom-in duration-500">
    <div class="flex flex-col items-center mb-10">
      <div class="bg-spotify-green p-4 rounded-full mb-4 shadow-lg shadow-spotify-green/20">
        <Music size={48} class="text-black" />
      </div>
      <h1 class="text-4xl font-extrabold text-white tracking-tighter">MuMa</h1>
      <p class="text-spotify-lightgray font-medium">Control Center Login</p>
    </div>
    
    <form on:submit|preventDefault={login} class="space-y-6">
      <div class="space-y-2">
        <label class="text-xs font-bold text-spotify-lightgray uppercase tracking-widest ml-1">Username</label>
        <input 
          type="text" 
          bind:value={username} 
          class="w-full bg-spotify-dark border border-white border-opacity-10 rounded-md p-4 text-white focus:outline-none focus:border-spotify-green transition-all"
          placeholder="admin"
        />
      </div>
      <div class="space-y-2">
        <label class="text-xs font-bold text-spotify-lightgray uppercase tracking-widest ml-1">Password</label>
        <input 
          type="password" 
          bind:value={password} 
          class="w-full bg-spotify-dark border border-white border-opacity-10 rounded-md p-4 text-white focus:outline-none focus:border-spotify-green transition-all"
          placeholder="••••••••"
        />
      </div>

      {#if loginError}
        <div class="bg-red-500 bg-opacity-10 border border-red-500 text-red-500 p-3 rounded-md text-sm font-bold animate-in shake duration-500">
          {loginError}
        </div>
      {/if}

      <button 
        type="submit" 
        disabled={isLoggingIn}
        class="w-full bg-spotify-green text-black font-extrabold py-4 rounded-full hover:scale-105 active:scale-95 transition-all shadow-lg shadow-spotify-green/10 disabled:opacity-50"
      >
        {isLoggingIn ? 'LOGGING IN...' : 'LOG IN'}
      </button>
    </form>
  </div>
</div>
