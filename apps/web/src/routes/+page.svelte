<script lang="ts">
  import Card from '$lib/ui/Card.svelte';
  import Button from '$lib/ui/Button.svelte';
</script>

<section class="grid">
  <Card title="Welcome to MuMa" subtitle="Unified operations for importing and analysing music.">
    <p>
      The control center bundles pipeline triggers, configuration tools and analytics into a single
      experience. Use the navigation above to jump straight into importer automation or explore the
      library insights from the scrobbler.
    </p>
    <div class="actions">
      <Button variant="primary" on:click={() => (window.location.href = '/importer')}>
        Manage importer jobs
      </Button>
      <Button variant="ghost" on:click={() => (window.location.href = '/scrobbler')}>
        View listening analytics
      </Button>
    </div>
  </Card>
</section>

<style>
  .grid {
    display: grid;
    gap: 2rem;
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
  }
</style>
