<script>
  const { activeView = 'home', onnavigate } = $props();

  const navItems = [
    { id: 'home', label: 'Home', icon: 'M12.5 3.5a.5.5 0 0 1 .5 0l9 5.25a.5.5 0 0 1 .25.433V20.5a.5.5 0 0 1-.5.5h-5a.5.5 0 0 1-.5-.5v-5a.5.5 0 0 0-.5-.5h-2a.5.5 0 0 0-.5.5v5a.5.5 0 0 1-.5.5h-5a.5.5 0 0 1-.5-.5V9.183a.5.5 0 0 1 .25-.433z' },
    { id: 'songs', label: 'Nummers', icon: 'M15.5 2.157a.5.5 0 0 0-.707 0l-12 12A.5.5 0 0 0 3 15h3v5.5a.5.5 0 0 0 .5.5h11a.5.5 0 0 0 .5-.5V15h3a.5.5 0 0 0 .207-.843l-12-12z' },
    { id: 'sets', label: 'Sets', icon: 'M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm1-13h-2v6h6v-2h-4z' },
    { id: 'playlists', label: 'Bibliotheek', icon: 'M3 22a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1h15a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H3zm13-2V4H4v16h12z' }
  ];

  /**
   * Triggers navigation to a specific view.
   *
   * @param {string} id - The view identifier.
   */
  function navigate(id) {
    if (onnavigate) onnavigate(id);
  }
</script>

<nav class="flex justify-around items-center bg-black border-t border-[#282828] pb-safe pt-2">
  {#each navItems as item (item.id)}
    <button
      class="flex flex-col items-center gap-1 bg-transparent border-none py-2 px-4 cursor-pointer transition-colors {activeView === item.id || (item.id === 'playlists' && ['playlists', 'artists', 'albums', 'genres'].includes(activeView)) ? 'text-white' : 'text-[#b3b3b3]'}"
      onclick={() => navigate(item.id)}
    >
      <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor">
        <path d={item.icon}></path>
      </svg>
      <span class="text-[10px] font-medium">{item.label}</span>
    </button>
  {/each}
</nav>

<style>
  .pb-safe {
    padding-bottom: env(safe-area-inset-bottom, 0);
  }
</style>
