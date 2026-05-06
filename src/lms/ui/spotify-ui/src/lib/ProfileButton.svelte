<script>
  import { onMount } from 'svelte';

  export let onNavigate;

  let isOpen = false;
  const username = 'Gebruiker';

  function toggleDropdown() {
    isOpen = !isOpen;
  }

  function handleLogout() {
    // Bestaande logout logica: meestal is dat het legen van de authParams of een redirect
    // Voor nu even simpel:
    localStorage.removeItem('lmsAuth');
    window.location.reload();
  }

  // Sluit dropdown bij klikken buiten
  function handleClickOutside(event) {
    if (isOpen && !event.target.closest('.profile-menu-container')) {
      isOpen = false;
    }
  }

  onMount(() => {
    window.addEventListener('click', handleClickOutside);
    return () => window.removeEventListener('click', handleClickOutside);
  });
</script>

<div class="relative profile-menu-container">
  <button 
    class="flex items-center gap-2 bg-black/70 hover:bg-[#282828] rounded-full p-0.5 pr-2 transition-colors cursor-pointer border-none text-white"
    on:click={toggleDropdown}
    aria-haspopup="true"
    aria-expanded={isOpen}
  >
    <div class="w-7 h-7 bg-[#535353] rounded-full flex items-center justify-center overflow-hidden">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
        <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"></path>
      </svg>
    </div>
    <span class="text-sm font-bold hidden md:inline">{username}</span>
    <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" class="transition-transform {isOpen ? 'rotate-180' : ''}">
      <path d="M4 6l4 4 4-4"></path>
    </svg>
  </button>

  {#if isOpen}
    <div class="absolute right-0 mt-2 w-48 bg-[#282828] rounded shadow-lg py-1 z-50">
      <button 
        class="w-full text-left px-4 py-3 text-sm hover:bg-[#3e3e3e] transition-colors border-none bg-transparent text-white cursor-pointer flex justify-between items-center"
        on:click={() => { isOpen = false; onNavigate('settings'); }}
      >
        Instellingen
        <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
            <path d="M14 8.5V7.5H11.55C11.39 6.78 11.09 6.12 10.67 5.54L12.41 3.8L11.7 3.09L9.96 4.83C9.38 4.41 8.72 4.11 8 3.95V1.5H7V3.95C6.28 4.11 5.62 4.41 5.04 4.83L3.3 3.09L2.59 3.8L4.33 5.54C3.91 6.12 3.61 6.78 3.45 7.5H1V8.5H3.45C3.61 9.22 3.91 9.88 4.33 10.46L2.59 12.2L3.3 12.91L5.04 11.17C5.62 11.59 6.28 11.89 7 12.05V14.5H8V12.05C8.72 11.89 9.38 11.59 9.96 11.17L11.7 12.91L12.41 12.2L10.67 10.46C11.09 9.88 11.39 9.22 11.55 8.5H14ZM7.5 10C6.12 10 5 8.88 5 7.5C5 6.12 6.12 5 7.5 5C8.88 5 10 6.12 10 7.5C10 8.88 8.88 10 7.5 10Z"></path>
        </svg>
      </button>
      <div class="h-[1px] bg-[#3e3e3e] mx-1 my-1"></div>
      <button 
        class="w-full text-left px-4 py-3 text-sm hover:bg-[#3e3e3e] transition-colors border-none bg-transparent text-white cursor-pointer"
        on:click={handleLogout}
      >
        Uitloggen
      </button>
    </div>
  {/if}
</div>
