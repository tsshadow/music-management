<script>
  import { visibleSortOptions, allSortOptions, authParams } from '../store.js';

  let importing = $state(false);
  let importMessage = $state('');
  let importError = $state(false);

  /**
   * Toggles the visibility of a specific sort option for a given type.
   *
   * @param {string} type - The content type (songs, albums, or artists).
   * @param {string} id - The sort option identifier.
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

<section class="max-w-3xl pb-20">
  <h3 class="text-2xl font-bold mb-2">Geavanceerde Opties</h3>
  <p class="text-[#b3b3b3] mb-8">Kies welke sorteeropties zichtbaar moeten zijn in de interface.</p>

  <div class="flex flex-col gap-8">
    {#each Object.entries(allSortOptions) as [type, options]}
      <div>
        <h4 class="text-sm font-bold text-[#b3b3b3] uppercase tracking-wider mb-4">
          {type === 'songs' ? 'Nummers' : type === 'albums' ? 'Albums' : 'Artiesten'}
        </h4>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          {#each options as option}
            <label class="flex items-center gap-3 p-3 bg-[#181818] rounded-md border border-transparent hover:border-[#3e3e3e] cursor-pointer transition-colors">
              <input
                type="checkbox"
                class="w-5 h-5 accent-brand"
                checked={$visibleSortOptions[type].includes(option.id)}
                onchange={() => toggleOption(type, option.id)}
              />
              <span class="text-white font-medium">{option.label}</span>
            </label>
          {/each}
        </div>
      </div>
    {/each}
  </div>

  <div class="mt-12 pt-8 border-t border-[#3e3e3e]">
    <h3 class="text-2xl font-bold mb-2">Onderhoud</h3>
    <p class="text-[#b3b3b3] mb-6">Handmatige onderhoudstaken voor externe diensten.</p>

    <div class="bg-[#181818] p-6 rounded-lg border border-[#3e3e3e]">
      <h4 class="text-white font-bold mb-2">ListenBrainz Import</h4>
      <p class="text-sm text-[#b3b3b3] mb-4">
        Synchroniseer je luistergeschiedenis handmatig vanaf ListenBrainz. Dit gebeurt normaal gesproken periodiek op de achtergrond.
      </p>
      <button
        onclick={importFromListenBrainz}
        disabled={importing}
        class="bg-brand hover:scale-105 active:scale-95 text-black font-bold py-3 px-8 rounded-full transition-all disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {importing ? 'Importeren...' : 'Nu importeren'}
      </button>

      {#if importMessage}
        <p class="mt-4 text-sm {importError ? 'text-red-500' : 'text-brand'}">
          {importMessage}
        </p>
      {/if}
    </div>
  </div>
</section>
