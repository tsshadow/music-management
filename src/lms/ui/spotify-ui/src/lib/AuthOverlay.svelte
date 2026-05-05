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
<div class="overlay">
  <div class="modal">
    <h2>LMS Inloggen</h2>
    <p>Voer je Subsonic inloggegevens in om muziek te kunnen streamen.</p>
    
    {#if error}
      <div class="error-message">{error}</div>
    {/if}

    <div class="input-group">
      <label>Gebruikersnaam</label>
      <input type="text" bind:value={username} placeholder="Username" disabled={isLoading} />
    </div>
    <div class="input-group">
      <label>Wachtwoord</label>
      <input type="password" bind:value={password} placeholder="Password" disabled={isLoading} on:keydown={(e) => e.key === 'Enter' && verifyLogin()} />
    </div>
    <button on:click={verifyLogin} disabled={isLoading}>
      {isLoading ? 'Verificeren...' : 'Verbinden'}
    </button>
  </div>
</div>
{/if}

<style>
  .overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background: rgba(0,0,0,0.8);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 1000;
  }

  .modal {
    background: #282828;
    padding: 32px;
    border-radius: 8px;
    width: 400px;
    display: flex;
    flex-direction: column;
    gap: 20px;
  }

  h2 { margin: 0; }

  .error-message {
    background-color: #e91429;
    color: white;
    padding: 10px;
    border-radius: 4px;
    font-size: 14px;
  }

  .input-group {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  label {
    font-size: 12px;
    font-weight: 700;
    color: #b3b3b3;
    text-transform: uppercase;
  }

  input {
    background: #3e3e3e;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 12px;
    color: #fff;
    font-size: 14px;
  }

  input:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  input:focus {
    outline: none;
    border-color: #1db954;
  }

  button {
    background-color: #1db954;
    color: #000;
    border: none;
    border-radius: 500px;
    padding: 14px;
    font-size: 16px;
    font-weight: 700;
    cursor: pointer;
    transition: transform 0.2s;
  }

  button:disabled {
    background-color: #1ed76080;
    cursor: not-allowed;
    transform: none;
  }

  button:not(:disabled):hover {
    transform: scale(1.04);
  }
</style>
