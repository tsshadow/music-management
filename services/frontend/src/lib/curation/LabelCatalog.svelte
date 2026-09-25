<script>
  /**
   * The Catalogus section of the label edit page: per series (`DWX`, `DWXCD`, ...) the
   * range the library holds, how much of it is present, and the numbers in that range
   * that are not.
   *
   * Loads on its own so the rest of the page never waits for it, and keeps its own
   * error: the catalogue is read off a few thousand file paths on demand, and a
   * failure there says nothing about the label's rules above.
   *
   * The wording is deliberate. A number is "niet aanwezig", never "ontbreekt": a label
   * may skip numbers, and nothing here can tell a skipped number from one that was
   * never bought. Nothing is claimed before the lowest or after the highest number
   * held -- the "waargenomen bereik".
   */
  import { onMount } from 'svelte';
  import { SvelteSet } from 'svelte/reactivity';

  import { t } from '../i18n/index.js';
  import { RUNS_SHOWN, formatRuns, searchTerms, seriesHeader } from './catalogRuns.js';
  import { loadLabelCatalog } from './curationApi.js';

  let { name } = $props();

  let catalog = $state(null);
  let error = $state(null);
  let copied = $state(null);
  let copyError = $state(null);
  let expanded = new SvelteSet();

  onMount(async () => {
    try {
      catalog = await loadLabelCatalog(name);
    } catch (e) {
      error = e.message;
    }
  });

  function visibleRuns(series) {
    return expanded.has(series.prefix) ? series.absent_runs : series.absent_runs.slice(0, RUNS_SHOWN);
  }

  /**
   * Every absent number of the series to the clipboard, one per line, written in
   * full: `DWX0287–DWX0289` reads well but a search wants three separate terms.
   */
  async function copy(series) {
    copyError = null;
    try {
      await navigator.clipboard.writeText(searchTerms(series));
      copied = series.prefix;
      setTimeout(() => {
        if (copied === series.prefix) copied = null;
      }, 2000);
    } catch {
      copyError = $t('curation.copyFailed');
    }
  }
</script>

<section>
  <h2 class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text m-0">{$t('curation.catalog')}</h2>
  <p class="text-xs text-muma-spotify-text mt-1 mb-0">
    {$t('curation.catalogHelp')}
  </p>

  {#if error}
    <p class="text-xs text-red-400 mt-3 mb-0" role="alert">{$t('curation.catalogLoadFailed', { error })}</p>
  {:else if !catalog}
    <p class="text-xs text-muma-spotify-text mt-3 mb-0 animate-pulse">{$t('curation.catalogLoading')}</p>
  {:else}
    {#if catalog.series.length === 0}
      <p class="text-sm text-muma-spotify-text mt-3 mb-0">
        {$t('curation.catalogEmpty')}
      </p>
    {/if}
    {#if catalog.files_outside_root > 0}
      <p class="text-xs text-muma-spotify-text mt-2 mb-0">
        {$t('curation.filesOutsideRoot', { count: catalog.files_outside_root })}
      </p>
    {/if}

    <div class="flex flex-col gap-5 mt-3">
      {#each catalog.series as series (series.prefix)}
        <div>
          <div class="flex items-center justify-between gap-3 flex-wrap">
            <span class="text-sm font-bold text-white tabular-nums">{seriesHeader(series)}</span>
            {#if !series.absent_truncated && series.absent_count > 0}
              <button
                class="bg-transparent text-white text-xs font-bold border border-white/20 rounded-full px-3 py-1 cursor-pointer hover:scale-105 disabled:opacity-40"
                onclick={() => copy(series)}
              >
                {copied === series.prefix ? $t('curation.copied') : $t('curation.copyAsTerms')}
              </button>
            {/if}
          </div>
          <div class="h-1.5 w-full bg-white/5 rounded-full overflow-hidden mt-2">
            <div class="h-full bg-brand rounded-full" style="width: {Math.round(series.coverage * 100)}%"></div>
          </div>

          {#if series.absent_truncated}
            <p class="text-xs text-muma-spotify-text mt-2 mb-0">
              {$t('curation.absentTruncated', { count: series.absent_count })}
            </p>
          {:else if series.absent_count === 0}
            <p class="text-xs text-muma-spotify-text mt-2 mb-0">
              {$t('curation.allPresent')}
            </p>
          {:else}
            <p class="text-xs text-muma-spotify-text mt-2 mb-0 break-words">
              <span class="text-white">{$t('curation.notPresent', { count: series.absent_count })}</span>
              <span class="font-mono">{formatRuns(series, visibleRuns(series))}</span>
              {#if series.absent_runs.length > RUNS_SHOWN && !expanded.has(series.prefix)}
                <button
                  class="bg-transparent border-none text-brand text-xs font-bold cursor-pointer p-0 ml-1"
                  onclick={() => expanded.add(series.prefix)}
                >
                  {$t('curation.showAll', { count: series.absent_runs.length })}
                </button>
              {/if}
            </p>
          {/if}

          {#if series.variants.length > 0}
            <p class="text-xs text-muma-spotify-text mt-2 mb-0 break-words">
              {$t('curation.variants')}
              {#each series.variants as variant (variant.catid)}
                <span class="font-mono mr-2" title={variant.release_folder}>{variant.catid}</span>
              {/each}
            </p>
          {/if}
        </div>
      {/each}

      {#if catalog.other.length > 0}
        <p class="text-xs text-muma-spotify-text mt-0 mb-0 break-words">
          {$t('curation.otherCatids')}
          {#each catalog.other as entry (entry.catid)}
            <span class="font-mono mr-2" title={entry.release_folder}>{entry.catid}</span>
          {/each}
        </p>
      {/if}
    </div>
    {#if copyError}
      <p class="text-xs text-red-400 mt-2 mb-0" role="alert">{copyError}</p>
    {/if}
  {/if}
</section>
