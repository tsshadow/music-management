<script>
  import { onMount } from 'svelte';
  import { authParams } from '../store.js';

  let libraries = $state([]);
  let isLoading = $state(true);
  let showAddModal = $state(false);
  let newLibName = $state("");
  let newLibPath = $state("");

  /**
   * Loads the list of configured music folders/libraries from the server.
   */
  async function loadLibraries() {
    isLoading = true;
    try {
      const response = await fetch(`/api/admin/libraries?${$authParams}`);
      if (response.ok) {
        libraries = await response.json();
      } else {
        // Fallback to Subsonic if MuMa endpoint fails
        const subResponse = await fetch(`/rest/getMusicFolders?${$authParams}`);
        const data = await subResponse.json();
        const res = data['subsonic-response'];
        if (res && res.musicFolders) {
            libraries = Array.isArray(res.musicFolders.musicFolder)
            ? res.musicFolders.musicFolder
            : [res.musicFolders.musicFolder];
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      isLoading = false;
    }
  }

  /**
   * Adds a new library folder.
   */
  async function addLibrary() {
    if (!newLibName || !newLibPath) return;
    try {
      const response = await fetch(`/api/admin/libraries?${$authParams}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newLibName, path: newLibPath })
      });
      if (response.ok) {
        showAddModal = false;
        newLibName = "";
        newLibPath = "";
        loadLibraries();
      } else {
        alert("Fout bij toevoegen bibliotheek");
      }
    } catch (e) {
      console.error(e);
    }
  }

  /**
   * Deletes a library folder.
   * @param {number|string} id
   */
  async function deleteLibrary(id) {
    if (!confirm("Weet je zeker dat je deze bibliotheek wilt verwijderen?")) return;
    try {
      const response = await fetch(`/api/admin/libraries/${id}?${$authParams}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        loadLibraries();
      } else {
        alert("Fout bij verwijderen bibliotheek");
      }
    } catch (e) {
      console.error(e);
    }
  }

  /**
   * Starts a scan for the whole library.
   */
  async function startScan() {
    try {
      await fetch(`/rest/startScan?${$authParams}`);
      alert("Scan gestart!");
    } catch (e) {
      console.error(e);
    }
  }

  onMount(loadLibraries);
</script>

<section>
  <h3 class="text-2xl font-bold mb-6">Music Libraries</h3>

  {#if isLoading}
    <div class="text-[#b3b3b3]">Laden...</div>
  {:else}
    <div class="flex flex-col gap-4">
      {#each libraries as lib (lib.id)}
        <div class="bg-[#181818] rounded-lg p-6 hover:bg-[#282828] transition-colors border border-transparent hover:border-[#3e3e3e]">
          <div class="flex justify-between items-center">
            <div class="flex-1">
              <h4 class="font-bold text-lg text-white">{lib.name}</h4>
              <p class="text-sm text-[#b3b3b3] mt-1 font-mono">{lib.path || 'Pad niet beschikbaar'}</p>
            </div>
            <div class="flex gap-3">
              <button 
                onclick={startScan}
                class="bg-[#282828] text-white px-4 py-2 rounded-full font-bold hover:bg-[#3e3e3e] transition-colors cursor-pointer border-none text-sm"
              >Scan</button>
              <button 
                onclick={() => deleteLibrary(lib.id)}
                class="bg-red-500/10 text-red-500 px-4 py-2 rounded-full font-bold hover:bg-red-500/20 transition-colors cursor-pointer border-none text-sm"
              >Verwijderen</button>
            </div>
          </div>
        </div>
      {/each}

      {#if libraries.length === 0}
        <div class="bg-[#181818] rounded-lg p-10 text-center border-2 border-dashed border-[#282828]">
            <p class="text-[#b3b3b3]">Geen bibliotheken gevonden.</p>
        </div>
      {/if}

      <div class="mt-4 p-4 border-t border-[#282828]">
        <button 
            onclick={() => showAddModal = true}
            class="text-brand font-bold hover:underline cursor-pointer border-none bg-transparent flex items-center gap-2"
        >
            <span class="text-2xl">+</span> Bibliotheek toevoegen
        </button>
      </div>
    </div>
  {/if}
</section>

{#if showAddModal}
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
    <div class="bg-[#181818] p-8 rounded-xl w-full max-w-md border border-white/10 shadow-2xl">
      <h3 class="text-2xl font-bold mb-6">Bibliotheek toevoegen</h3>
      <div class="space-y-4">
        <div>
          <label class="block text-xs font-bold uppercase text-[#b3b3b3] mb-2">Naam</label>
          <input 
            type="text" 
            bind:value={newLibName}
            placeholder="Bijv. Mijn Muziek"
            class="w-full bg-[#3e3e3e] border-none rounded p-3 text-white focus:ring-2 focus:ring-brand outline-none"
          />
        </div>
        <div>
          <label class="block text-xs font-bold uppercase text-[#b3b3b3] mb-2">Pad</label>
          <input 
            type="text" 
            bind:value={newLibPath}
            placeholder="Bijv. /music/jazz"
            class="w-full bg-[#3e3e3e] border-none rounded p-3 text-white focus:ring-2 focus:ring-brand outline-none"
          />
        </div>
      </div>
      <div class="flex justify-end gap-4 mt-8">
        <button 
          onclick={() => showAddModal = false}
          class="bg-transparent text-white font-bold px-6 py-2 rounded-full hover:bg-white/5 transition-colors cursor-pointer border-none"
        >Annuleren</button>
        <button 
          onclick={addLibrary}
          class="bg-brand text-black font-bold px-8 py-2 rounded-full hover:scale-105 transition-transform cursor-pointer border-none"
        >Toevoegen</button>
      </div>
    </div>
  </div>
{/if}
