<script>
  import ProfileButton from './ProfileButton.svelte';
  import SearchBar from './SearchBar.svelte';
  import { activeView } from './store.js';

  const { greeting = "" } = $props();

  /**
   * Updates the global active view state.
   *
   * @param {string} view - The view identifier.
   */
  function handleNavigate(view) {
    activeView.set(view);
  }

</script>

<div class="flex items-center justify-between mb-6 sticky top-0 z-30 py-2 bg-[#121212]/90 backdrop-blur-md px-4 -mx-4">
  <div class="flex items-center gap-4 flex-grow">
    {#if $activeView === 'home'}
        <h1 class="text-xl md:text-3xl font-bold ml-2 whitespace-nowrap">{greeting}</h1>
    {/if}
    
    <SearchBar />
  </div>

  <ProfileButton onNavigate={handleNavigate} />
</div>
