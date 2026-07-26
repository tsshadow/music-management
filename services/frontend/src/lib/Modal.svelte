<script>
  import { onMount, onDestroy } from 'svelte';
  import { fade, scale } from 'svelte/transition';

  /**
   * @typedef {Object} Props
   * @property {string} [title] - Modal title.
   * @property {function(): void} onclose - Callback to close the modal.
   * @property {import('svelte').Snippet} [children] - Modal content.
   */

  /** @type {Props} */
  let { title = '', onclose, children } = $props();

  function handleKeydown(e) {
    if (e.key === 'Escape') {
      onclose();
    }
  }

  onMount(() => {
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', handleKeydown);
  });

  onDestroy(() => {
    document.body.style.overflow = '';
    window.removeEventListener('keydown', handleKeydown);
  });
</script>

<div 
  class="fixed inset-0 z-[100] flex items-center justify-center p-4 md:p-8"
  transition:fade={{ duration: 200 }}
>
  <!-- Backdrop -->
  <button 
    class="absolute inset-0 bg-black/80 backdrop-blur-sm w-full h-full cursor-default border-none" 
    onclick={onclose}
    aria-label="Modal sluiten"
  ></button>

  <!-- Modal Container -->
  <div 
    class="relative w-full max-w-4xl max-h-[90vh] bg-[#121212] rounded-xl shadow-2xl flex flex-col overflow-hidden border border-white/10"
    transition:scale={{ duration: 200, start: 0.95 }}
  >
    <!-- Header -->
    <div class="flex items-center justify-between p-6 border-b border-white/5">
      <h2 class="text-2xl font-bold m-0">{title}</h2>
      <button 
        class="text-[#b3b3b3] hover:text-white transition-colors"
        onclick={onclose}
        aria-label="Sluiten"
      >
        <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor">
          <path d="M18.3 5.71a.996.996 0 00-1.41 0L12 10.59 7.11 5.7a.996.996 0 10-1.41 1.41L10.59 12 5.7 16.89a.996.996 0 101.41 1.41L12 13.41l4.89 4.89a.996.996 0 101.41-1.41L13.41 12l4.89-4.89c.38-.38.38-1.02 0-1.4z"/>
        </svg>
      </button>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto p-6 custom-scrollbar">
      {#if children}
        {@render children()}
      {/if}
    </div>
  </div>
</div>

<style>
  .custom-scrollbar::-webkit-scrollbar {
    width: 12px;
  }
  .custom-scrollbar::-webkit-scrollbar-track {
    background: transparent;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb {
    background: #3e3e3e;
    border-radius: 6px;
    border: 3px solid #121212;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb:hover {
    background: #5a5a5a;
  }
</style>
