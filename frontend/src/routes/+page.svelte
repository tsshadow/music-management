<script>
import StepStarter from '$lib/StepStarter.svelte';
import JobsList from '$lib/JobsList.svelte';
import { initializeJobsContext } from '$lib/jobs-context';

initializeJobsContext();
</script>

<main>
  <h1>Music Importer</h1>
  <StepStarter />
  <JobsList />
</main>
