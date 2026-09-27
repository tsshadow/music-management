<script>
  /**
   * What a settings tab shows while its chunk is on its way (issue #119): the tab's own
   * geometry -- a title and subtitle, then two panels of label-and-control rows -- in skeleton
   * blocks, with the same density classes as the tabs, so nothing moves when the tab arrives.
   */
  import "./density.css";
  import Skeleton from '../loading/Skeleton.svelte';
</script>

<div class="settings-density max-w-4xl mx-auto pb-24" data-testid="settings-tab-loading" aria-busy="true">
  <header class="mb-8">
    <Skeleton class="h-7 w-48 mb-2" />
    <Skeleton class="h-3 w-72 max-w-full" />
  </header>
  <div class="flex flex-col gap-6">
    {#each [3, 2] as rows, panel (panel)}
      <section class="bg-muma-spotify-panel rounded-lg p-6 shadow-lg border border-white/5">
        <Skeleton class="h-4 w-32 mb-6" />
        <div class="flex flex-col gap-6">
          {#each Array.from({ length: rows }, (_, i) => i) as row (row)}
            <div class="flex items-center justify-between gap-4">
              <div class="flex min-w-0 flex-1 flex-col gap-1">
                <Skeleton class="h-3.5 w-40 max-w-full" />
                <Skeleton class="h-3 w-64 max-w-full" />
              </div>
              <Skeleton class="h-6 w-11 shrink-0 rounded-full" />
            </div>
          {/each}
        </div>
      </section>
    {/each}
  </div>
</div>
