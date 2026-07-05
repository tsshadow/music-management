<script>
  import { onMount } from 'svelte';
  import { visibleSortOptions, allSortOptions, authParams, credentials } from '../store.js';

  let importing = false;
  let importMessage = '';
  let importError = false;

  let subsonicToken = '';
  let isLoadingToken = true;
  let isSavingToken = false;

  let newPassword = '';
  let confirmPassword = '';
  let passwordMessage = '';
  let passwordError = false;
  let isChangingPassword = false;

  onMount(async () => {
    await fetchToken();
  });

  async function fetchToken() {
    isLoadingToken = true;
    try {
      const resp = await fetch(`/rest/getUser?${$authParams}&username=${encodeURIComponent($credentials.username)}`);
      const data = await resp.json();
      subsonicToken = data['subsonic-response']?.user?.subsonicToken || '';
    } catch (e) {
      console.error(e);
    } finally {
      isLoadingToken = false;
    }
  }

  async function updateToken(newToken) {
    isSavingToken = true;
    try {
      const resp = await fetch(`/rest/updateUser?${$authParams}&username=${encodeURIComponent($credentials.username)}&subsonicToken=${encodeURIComponent(newToken)}`);
      const data = await resp.json();
      if (data['subsonic-response']?.status === 'ok') {
        subsonicToken = newToken;
      }
    } catch (e) {
      console.error(e);
    } finally {
      isSavingToken = false;
    }
  }

  function generateToken() {
    const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
    let result = '';
    for (let i = 0; i < 16; i++) {
      result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    updateToken(result);
  }

  async function changePassword() {
    if (newPassword !== confirmPassword) {
      passwordMessage = 'Wachtwoorden komen niet overeen';
      passwordError = true;
      return;
    }
    if (newPassword.length < 4) {
      passwordMessage = 'Wachtwoord moet minimaal 4 tekens bevatten';
      passwordError = true;
      return;
    }

    isChangingPassword = true;
    passwordMessage = '';
    try {
      const resp = await fetch(`/rest/updateUser?${$authParams}&username=${encodeURIComponent($credentials.username)}&password=${encodeURIComponent(newPassword)}`);
      const data = await resp.json();
      if (data['subsonic-response']?.status === 'ok') {
        passwordMessage = 'Wachtwoord succesvol gewijzigd!';
        passwordError = false;
        newPassword = '';
        confirmPassword = '';
      } else {
        passwordMessage = 'Fout bij wijzigen wachtwoord';
        passwordError = true;
      }
    } catch (e) {
      passwordMessage = 'Netwerkfout';
      passwordError = true;
    } finally {
      isChangingPassword = false;
    }
  }

  /**
   * Toggles the visibility of a specific sort option for a given type.
   */
  function toggleOption(type, id) {
    visibleSortOptions.update(options => {
      const current = options[type];
      if (current.includes(id)) {
        options[type] = current.filter(i => i !== id);
      } else {
        options[type] = [...current, id];
      }
      return options;
    });
  }

  /**
   * Triggers a manual import from ListenBrainz via the backend.
   */
  async function importFromListenBrainz() {
    if (!$authParams) return;

    importing = true;
    importMessage = 'Import gestart...';
    importError = false;

    try {
      const response = await fetch(`/rest/spotifyImportFromListenBrainz?${$authParams}`);
      if (!response.ok) throw new Error('Netwerkfout');
      const data = await response.json();

      if (data['subsonic-response']?.status === 'ok') {
        importMessage = 'Synchronisatie is gestart op de achtergrond. Het kan even duren voordat alle nummers zichtbaar zijn.';
      } else {
        throw new Error(data['subsonic-response']?.error?.message || 'Onbekende fout');
      }
    } catch (e) {
      importError = true;
      importMessage = 'Fout bij importeren: ' + e.message;
    } finally {
      importing = false;
    }
  }
</script>

<div class="max-w-4xl pb-24">
  <header class="mb-8">
    <h1 class="text-3xl font-bold mb-2">Geavanceerd</h1>
    <p class="text-[#b3b3b3]">Beheer sorteeropties, beveiliging en onderhoud.</p>
  </header>

  <div class="flex flex-col gap-8">
    <!-- Security Section -->
    <section class="bg-[#181818] rounded-lg p-6 shadow-lg border border-white/5">
      <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">Beveiliging</h2>
      
      <div class="flex flex-col gap-8">
        <!-- Subsonic Token -->
        <div>
          <h3 class="text-lg font-bold mb-2">Subsonic API Sleutel</h3>
          <p class="text-sm text-[#b3b3b3] mb-4">
            Gebruik deze sleutel om in te loggen op externe apps zoals Ultrasonic of Magna zonder je hoofdwachtwoord te gebruiken.
          </p>
          
          <div class="flex items-center gap-4">
            <div class="bg-[#282828] px-4 py-2 rounded border border-white/10 font-mono text-brand flex-grow min-h-[42px] flex items-center">
              {isLoadingToken ? 'Laden...' : (subsonicToken || 'Geen sleutel ingesteld')}
            </div>
            {#if subsonicToken}
              <button 
                on:click={() => updateToken('')} 
                disabled={isSavingToken}
                class="text-red-500 hover:text-red-400 font-bold px-4"
              >
                Verwijder
              </button>
            {/if}
            <button 
              on:click={generateToken} 
              disabled={isSavingToken}
              class="bg-white text-black font-bold py-2 px-6 rounded-full hover:scale-105 transition-transform whitespace-nowrap"
            >
              {subsonicToken ? 'Nieuwe sleutel' : 'Genereer sleutel'}
            </button>
          </div>
        </div>

        <!-- Change Password -->
        <div class="pt-8 border-t border-white/5">
          <h3 class="text-lg font-bold mb-4">Wachtwoord Wijzigen</h3>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-2xl">
            <div class="flex flex-col gap-2">
              <label class="text-xs font-bold text-[#b3b3b3] uppercase">Nieuw Wachtwoord</label>
              <input 
                type="password" 
                bind:value={newPassword}
                class="bg-[#282828] text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand" 
              />
            </div>
            <div class="flex flex-col gap-2">
              <label class="text-xs font-bold text-[#b3b3b3] uppercase">Bevestig Wachtwoord</label>
              <input 
                type="password" 
                bind:value={confirmPassword}
                class="bg-[#282828] text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand" 
              />
            </div>
          </div>
          <button 
            on:click={changePassword}
            disabled={isChangingPassword || !newPassword}
            class="mt-6 bg-[#333] hover:bg-[#444] text-white font-bold py-2 px-8 rounded-full transition-colors disabled:opacity-50"
          >
            {isChangingPassword ? 'Wijzigen...' : 'Wachtwoord Bijwerken'}
          </button>
          {#if passwordMessage}
            <p class="mt-2 text-sm {passwordError ? 'text-red-500' : 'text-brand'}">{passwordMessage}</p>
          {/if}
        </div>
      </div>
    </section>

    <!-- Sort Options -->
    <section class="bg-[#181818] rounded-lg p-6 shadow-lg border border-white/5">
      <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">Sorteeropties</h2>
      <p class="text-[#b3b3b3] mb-8 text-sm">Kies welke sorteeropties zichtbaar moeten zijn in de interface.</p>

      <div class="flex flex-col gap-8">
        {#each Object.entries(allSortOptions) as [type, options]}
          <div>
            <h4 class="text-sm font-bold text-[#b3b3b3] uppercase tracking-wider mb-4">
              {type === 'songs' ? 'Nummers' : type === 'albums' ? 'Albums' : 'Artiesten'}
            </h4>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
              {#each options as option}
                <label class="flex items-center gap-3 p-3 bg-[#282828] rounded-md border border-transparent hover:border-[#3e3e3e] cursor-pointer transition-colors">
                  <input
                    type="checkbox"
                    class="w-5 h-5 accent-brand"
                    checked={$visibleSortOptions[type].includes(option.id)}
                    on:change={() => toggleOption(type, option.id)}
                  />
                  <span class="text-white font-medium">{option.label}</span>
                </label>
              {/each}
            </div>
          </div>
        {/each}
      </div>
    </section>

    <!-- Maintenance Section -->
    <section class="bg-[#181818] rounded-lg p-6 shadow-lg border border-white/5">
      <h2 class="text-xl font-bold mb-2 border-b border-white/10 pb-2">Onderhoud</h2>
      <p class="text-[#b3b3b3] mb-6 text-sm">Handmatige onderhoudstaken voor externe diensten.</p>

      <div class="bg-[#282828] p-6 rounded-lg border border-white/5">
        <h4 class="text-white font-bold mb-2">ListenBrainz Import</h4>
        <p class="text-sm text-[#b3b3b3] mb-4">
          Synchroniseer je luistergeschiedenis handmatig vanaf ListenBrainz. Dit gebeurt normaal gesproken periodiek op de achtergrond.
        </p>
        <button
          on:click={importFromListenBrainz}
          disabled={importing}
          class="bg-[#333] hover:bg-[#444] text-white font-bold py-3 px-8 rounded-full transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {importing ? 'Importeren...' : 'Nu importeren'}
        </button>

        {#if importMessage}
          <p class="mt-4 text-sm {importError ? 'text-red-500' : 'text-brand'}">
            {importMessage}
          </p>
        {/if}
      </div>
    </section>
  </div>
</div>

<style>
  .text-brand { color: #1ed760; }
  .bg-brand { background-color: #1ed760; }
</style>
