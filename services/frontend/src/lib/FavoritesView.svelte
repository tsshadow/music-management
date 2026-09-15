<script>
  import { t } from './i18n/index.js';
  import PresetGrid from './PresetGrid.svelte';

  /**
   * The phone's favourites destination. The page owns the grid and the create action;
   * PresetGrid supplies only preset tiles, leaving room for other favourite kinds later.
   */
  const { presets = [], tints = {}, canCreate = false, onnavigate } = $props();
</script>

<section class="flex flex-col gap-4" data-testid="favorites-view">
  <header class="flex items-center justify-between gap-3">
    <h2 class="text-base font-bold m-0">{$t('nav.favorites')}</h2>
    {#if canCreate}
      <button type="button" class="bg-transparent border-none text-white text-sm font-medium py-3 cursor-pointer" onclick={() => onnavigate('new-preset')}>
        + {$t('presetBuilder.new')}
      </button>
    {/if}
  </header>
  <div class="grid grid-cols-2 gap-2">
    <PresetGrid {presets} {tints} compact onopen={(preset) => onnavigate(`preset:${preset.id}`)} />
  </div>
</section>
