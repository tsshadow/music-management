<script>
import { getJobsContext } from '$lib/jobs-context';

const { jobs, stop } = getJobsContext();
</script>

<h2>Running Jobs</h2>
<ul>
  {#each $jobs as job}
    <li>
      {job.step} – {job.id}
      <button on:click={() => stop(job.id)}>Stop</button>
    </li>
  {/each}
</ul>
