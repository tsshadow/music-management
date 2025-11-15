<script lang="ts">
  /**
   * Card is a surface container with padding and elevated styling used across the MuMa dashboard.
   */
  export let title: string | null = null;
  export let subtitle: string | null = null;
</script>

<section class="card">
  {#if title}
    <header>
      <div class="heading">
        <h2>{title}</h2>
        {#if subtitle}
          <p>{subtitle}</p>
        {/if}
      </div>
      <slot name="actions" />
    </header>
  {/if}
  <slot />
</section>

<style>
  .card {
    background: var(--color-surface);
    border-radius: var(--radius-base);
    box-shadow: var(--shadow-lg);
    padding: 1.75rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
  }

  .heading {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  header h2 {
    font-size: 1.25rem;
    margin: 0;
  }

  header p {
    color: var(--color-muted);
    margin: 0.25rem 0 0;
  }
</style>
