<script>
import { getJobsContext } from '$lib/jobs-context';

const { jobs } = getJobsContext();
</script>

<h2>Running Jobs</h2>
<ul>
  {#each $jobs as job}
    <li>{job.step} – {job.id}</li>
  {/each}
</ul>
