<script>
  import { t } from '../../i18n/index.js';
  import { onMount } from 'svelte';
  import { authParams, mumaApiUrl, restUrl } from '../../store.js';

  const { onMessage, onError } = $props();

  let libraries = $state([]);
  let isLoading = $state(true);
  let showAddModal = $state(false);
  let newLibName = $state('');
  let newLibPath = $state('');

  /**
   * Loads the configured media libraries. The muma bridge is the only source
   * that also returns the on-disk path; the Subsonic fallback is name-only.
   */
  async function loadLibraries() {
    if (!$authParams) {
      isLoading = false;
      return;
    }
    isLoading = true;
    try {
      const response = await fetch(`${$mumaApiUrl}/api/admin/libraries?${$authParams}`);
      if (response.ok) {
        libraries = await response.json();
      } else {
        const subResponse = await fetch(restUrl(`/rest/getMusicFolders?${$authParams}`));
        const data = await subResponse.json();
        const folders = data['subsonic-response']?.musicFolders?.musicFolder;
        libraries = folders ? (Array.isArray(folders) ? folders : [folders]) : [];
      }
    } catch (e) {
      console.error(e);
      onError($t('management.libraries.loadFailed'));
    } finally {
      isLoading = false;
    }
  }

  async function addLibrary() {
    if (!newLibName || !newLibPath) return;
    try {
      const response = await fetch(`${$mumaApiUrl}/api/admin/libraries?${$authParams}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newLibName, path: newLibPath })
      });
      if (response.ok) {
        onMessage($t('management.libraries.added', { name: newLibName }));
        showAddModal = false;
        newLibName = '';
        newLibPath = '';
        loadLibraries();
      } else {
        onError(await response.text() || $t('management.libraries.addFailed'));
      }
    } catch (e) {
      console.error(e);
      onError($t('management.libraries.addNetworkError'));
    }
  }

  async function deleteLibrary(lib) {
    if (!confirm($t('management.libraries.confirmDelete', { name: lib.name }))) return;
    try {
      const response = await fetch(`${$mumaApiUrl}/api/admin/libraries/${lib.id}?${$authParams}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        onMessage($t('management.libraries.deleted', { name: lib.name }));
        loadLibraries();
      } else {
        onError(await response.text() || $t('management.libraries.deleteFailed'));
      }
    } catch (e) {
      console.error(e);
      onError($t('management.libraries.deleteNetworkError'));
    }
  }

  onMount(loadLibraries);
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
  <header>
    <h2 class="text-4xl font-extrabold mb-2">📚 {$t('management.tabs.libraries')}</h2>
    <p class="text-muma-spotify-text">{$t('management.libraries.subtitle')}</p>
  </header>

  {#if !$authParams}
    <div class="bg-muma-spotify-panel p-8 rounded-xl border border-white/5 text-center">
      <h3 class="text-xl font-bold mb-2">{$t('management.libraries.noConnection')}</h3>
      <p class="text-muma-spotify-text">
        {$t('management.libraries.noConnectionHelp')}
      </p>
    </div>
  {:else if isLoading}
    <div class="text-muma-spotify-text">{$t('common.loading')}</div>
  {:else}
    <div class="flex flex-col gap-4">
      {#each libraries as lib (lib.id)}
        <div class="bg-muma-spotify-panel rounded-xl p-6 border border-white/5 hover:border-white/10 transition-colors">
          <div class="flex justify-between items-center">
            <div class="flex-1 min-w-0">
              <h4 class="font-bold text-lg text-white">{lib.name}</h4>
              <p class="text-sm text-muma-spotify-text mt-1 font-mono truncate">{lib.path || $t('management.libraries.pathBridgeOnly')}</p>
            </div>
            <button
              onclick={() => deleteLibrary(lib)}
              class="bg-red-500/10 text-red-500 px-4 py-2 rounded-full font-bold hover:bg-red-500/20 transition-colors cursor-pointer border-none text-sm"
            >
              {$t('common.remove')}
            </button>
          </div>
        </div>
      {/each}

      {#if libraries.length === 0}
        <div class="bg-muma-spotify-panel rounded-xl p-10 text-center border-2 border-dashed border-muma-spotify-light">
          <p class="text-muma-spotify-text">{$t('management.libraries.empty')}</p>
        </div>
      {/if}

      <div class="mt-4 pt-4 border-t border-muma-spotify-light">
        <button
          onclick={() => (showAddModal = true)}
          class="text-brand font-bold hover:underline cursor-pointer border-none bg-transparent flex items-center gap-2"
        >
          <span class="text-2xl">+</span> {$t('management.libraries.add')}
        </button>
      </div>
    </div>
  {/if}
</section>

{#if showAddModal}
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
    <div class="bg-muma-spotify-panel p-8 rounded-xl w-full max-w-md border border-white/10 shadow-2xl">
      <h3 class="text-2xl font-bold mb-6">{$t('management.libraries.add')}</h3>
      <div class="space-y-4">
        <div>
          <label for="lib-name" class="block text-xs font-bold uppercase text-muma-spotify-text mb-2">{$t('management.libraries.name')}</label>
          <input
            id="lib-name"
            type="text"
            bind:value={newLibName}
            placeholder={$t('management.libraries.namePlaceholder')}
            class="w-full bg-muma-spotify-highlight border-none rounded p-3 text-white focus:ring-2 focus:ring-brand outline-none"
          />
        </div>
        <div>
          <label for="lib-path" class="block text-xs font-bold uppercase text-muma-spotify-text mb-2">{$t('management.libraries.path')}</label>
          <input
            id="lib-path"
            type="text"
            bind:value={newLibPath}
            placeholder={$t('management.libraries.pathPlaceholder')}
            class="w-full bg-muma-spotify-highlight border-none rounded p-3 text-white focus:ring-2 focus:ring-brand outline-none"
          />
        </div>
      </div>
      <div class="flex justify-end gap-4 mt-8">
        <button
          onclick={() => (showAddModal = false)}
          class="bg-transparent text-white font-bold px-6 py-2 rounded-full hover:bg-white/5 transition-colors cursor-pointer border-none"
        >
          {$t('common.cancel')}
        </button>
        <button
          onclick={addLibrary}
          class="bg-brand text-black font-bold px-8 py-2 rounded-full hover:scale-105 transition-transform cursor-pointer border-none"
        >
          {$t('common.add')}
        </button>
      </div>
    </div>
  </div>
{/if}
