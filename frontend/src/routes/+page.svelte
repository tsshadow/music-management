<script>
import StepStarter from '$lib/StepStarter.svelte';
import JobsList from '$lib/JobsList.svelte';
import { initializeJobsContext } from '$lib/jobs-context';

initializeJobsContext();
</script>

<main class="container mx-auto p-8">
  <h1 class="mb-8 text-center text-4xl font-bold">Music Importer</h1>
  <StepStarter />
  <JobsList />
</main>
