<script>
  /**
   * One section of a page, loading on its own: its skeleton while the first answer is on its
   * way, one error line with a retry pill when it failed, its content otherwise. A section that
   * already shows content keeps showing it while it refreshes -- the caller passes `ready` then
   * (styleguide, Loading States: Refresh, Section errors).
   *
   * @typedef {'loading'|'error'|'ready'} SectionStatus
   * @property {SectionStatus} status
   * @property {() => void} [onretry] - Without it the error line has no button.
   * @property {import('svelte').Snippet} [skeleton]
   * @property {import('svelte').Snippet} [children]
   */
  import { t } from '../i18n/index.js';

  const { status = 'ready', onretry, skeleton, children } = $props();
</script>

{#if status === 'loading'}
  {@render skeleton?.()}
{:else if status === 'error'}
  <div class="flex flex-col items-center gap-3 py-6 text-center" role="alert" data-testid="section-error">
    <p class="text-sm text-muma-spotify-muted m-0">{$t('common.sectionFailed')}</p>
    {#if onretry}
      <button
        class="bg-transparent border border-muma-spotify-muted text-white px-8 py-2 rounded-[24px] font-bold cursor-pointer transition-all hover:border-white hover:scale-[1.04]"
        onclick={() => onretry()}
      >{$t('common.retry')}</button>
    {/if}
  </div>
{:else}
  {@render children?.()}
{/if}
