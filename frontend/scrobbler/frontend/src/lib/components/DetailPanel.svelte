<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  export let title: string;
  export let open = false;
  export let loading = false;
  export let error: string | null = null;

  const dispatch = createEventDispatcher<{ close: void }>();

  function close() {
    dispatch('close');
  }

  function onOverlayClick(event: MouseEvent) {
    if (event.currentTarget === event.target) {
      close();
    }
  }
</script>

{#if open}
  <div class="overlay" role="presentation" on:click={onOverlayClick}>
    <div class="panel" role="dialog" aria-modal="true" aria-labelledby="panel-title">
      <header>
        <h3 id="panel-title">{title}</h3>
        <button type="button" class="close" on:click={close} aria-label="Close details">×</button>
      </header>
      <div class="content">
        {#if loading}
          <p class="status">Bezig met laden…</p>
        {:else if error}
          <p class="status error">{error}</p>
        {:else}
          <slot />
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 1.5rem;
  }

  .panel {
    width: min(640px, 100%);
    max-height: 90vh;
    overflow-y: auto;
    background: rgba(10, 10, 20, 0.95);
    border-radius: 1rem;
    padding: 1.5rem;
    box-shadow: 0 2rem 3rem rgba(0, 0, 0, 0.4);
  }

  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1rem;
  }

  h3 {
    margin: 0;
    font-size: 1.4rem;
  }

  .close {
    background: none;
    border: none;
    color: var(--text-color);
    font-size: 1.5rem;
    cursor: pointer;
  }

  .content {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .status {
    color: rgba(255, 255, 255, 0.75);
  }

  .status.error {
    color: #ff9090;
  }
</style>
