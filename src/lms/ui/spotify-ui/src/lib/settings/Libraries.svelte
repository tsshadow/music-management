<script>
  import { onMount } from 'svelte';
  import { authParams } from '../store.js';

  let libraries = [];
  let isLoading = true;

  /**
   * Loads the list of configured music folders/libraries from the server.
   */
  async function loadLibraries() {
    try {
      const response = await fetch(`/rest/getMusicFolders?${$authParams}`);
      const data = await response.json();
      const res = data['subsonic-response'];
      if (res && res.musicFolders) {
        libraries = Array.isArray(res.musicFolders.musicFolder)
          ? res.musicFolders.musicFolder
          : [res.musicFolders.musicFolder];
      }
    } catch (e) {
      console.error(e);
    } finally {
      isLoading = false;
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
              <button class="bg-[#282828] text-white px-4 py-2 rounded-full font-bold hover:bg-[#3e3e3e] transition-colors cursor-pointer border-none text-sm">Scan</button>
              <button class="bg-white text-black px-4 py-2 rounded-full font-bold hover:scale-105 transition-transform cursor-pointer border-none text-sm">Manage</button>
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
        <button class="text-brand font-bold hover:underline cursor-pointer border-none bg-transparent flex items-center gap-2">
            <span class="text-2xl">+</span> Add Library
        </button>
      </div>
    </div>
  {/if}
</section>
