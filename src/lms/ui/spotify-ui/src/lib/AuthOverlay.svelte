<script>
  import { credentials } from './store.js';

  let username = '';
  let password = '';

  function save() {
    credentials.update(c => ({ ...c, username, password }));
    // Store in localStorage for persistence
    localStorage.setItem('lms_username', username);
    localStorage.setItem('lms_password', password);
  }

  // Load from localStorage on init
  import { onMount } from 'svelte';
  onMount(() => {
    const u = localStorage.getItem('lms_username');
    const p = localStorage.getItem('lms_password');
    if (u && p) {
      username = u;
      password = p;
      save();
    }
  });
</script>

{#if !$credentials.username}
<div class="overlay">
  <div class="modal">
    <h2>LMS Inloggen</h2>
    <p>Voer je Subsonic inloggegevens in om muziek te kunnen streamen.</p>
    <div class="input-group">
      <label>Gebruikersnaam</label>
      <input type="text" bind:value={username} placeholder="Username" />
    </div>
    <div class="input-group">
      <label>Wachtwoord</label>
      <input type="password" bind:value={password} placeholder="Password" />
    </div>
    <button on:click={save}>Verbinden</button>
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

  button:hover {
    transform: scale(1.04);
  }
</style>
