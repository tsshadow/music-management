<script lang="ts">
  /** Combined importer console page that surfaces job controls and configuration management. */
  import MatrixBackground from './MatrixBackground.svelte';
  import StepStarter from './StepStarter.svelte';
  import JobsList from './JobsList.svelte';
  import ConfigEditor from './ConfigEditor.svelte';
  import { initializeJobsContext } from './jobs-context';

  initializeJobsContext();
</script>

<section class="importer-shell">
  <MatrixBackground />
  <main class="importer-panel container mx-auto space-y-8 p-8">
    <h1 class="mb-8 text-center text-4xl font-bold text-green-400">MuMa Importer</h1>
    <StepStarter />
    <ConfigEditor />
    <JobsList />
  </main>
</section>

<style>
  .importer-shell {
    position: relative;
  }

  .importer-panel {
    position: relative;
    z-index: 10;
  }
</style>
