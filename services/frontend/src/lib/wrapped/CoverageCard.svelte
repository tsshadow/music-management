<script>
  /**
   * The last card of every tab: how many listens the tab counted, how much of the data had the
   * fields the cards need, and every card that was left out, with its reason.
   */
  import { t } from '../i18n/index.js';

  const { model } = $props();
</script>

<article
  class="flex flex-col gap-4 rounded-lg p-6 md:p-8 bg-muma-spotify-panel snap-start md:col-span-2"
  data-testid="wrapped-coverage"
>
  <p class="m-0 text-sm font-bold uppercase tracking-[0.1em] text-white/80">{$t('wrapped.coverage.label')}</p>
  <p class="m-0 text-base text-white/90">{model.sentence}</p>
  {#if model.shares.length > 0}
    <dl class="m-0 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
      {#each model.shares as share (share.label)}
        <dt class="text-muma-spotify-text">{share.label}</dt>
        <dd class="m-0 text-right">{share.value}</dd>
      {/each}
    </dl>
  {/if}
  {#if model.leftOut.length > 0}
    <h3 class="m-0 text-base font-bold">{$t('wrapped.coverage.leftOut')}</h3>
    <ul class="m-0 p-0 list-none flex flex-col gap-1 text-sm" data-testid="wrapped-left-out">
      {#each model.leftOut as entry (entry.id)}
        <li><span class="font-bold">{entry.label}</span> <span class="text-muma-spotify-text">{entry.reason}</span></li>
      {/each}
    </ul>
  {/if}
</article>
