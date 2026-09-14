<script>
  import { t } from './i18n/index.js';
  import { presetSummary } from './presets.js';
  import { tintFor } from './genreTints.js';

  /**
   * The preset tiles on the home screen: one coloured block per saved query, the way the
   * Kotlin app's home grid has shown them. Tapping one opens its list (`preset:<id>`), where
   * the play button is; the tile itself never starts playback, so a mis-tap while scrolling
   * costs nothing.
   *
   * Colour comes from the first genre's tint when MuMa has one, so "Raw Hardstyle" is the same
   * red here as on the genre page, and from a fixed palette keyed on the name otherwise.
   */
  const { presets = [], tints = {}, onopen } = $props();

  /** The Kotlin tile palette, minus the near-blacks that vanish on this background. */
  const PALETTE = [
    '#1E3264', '#8B0000', '#006400', '#4B0082', '#8B4513',
    '#556B2F', '#D2691E', '#B22222', '#6A5ACD', '#2C3E50',
    '#8C1932', '#477D95', '#BC5900', '#503750', '#148A08',
  ];

  function colorFor(preset) {
    const tint = preset.genres.length ? tintFor(tints, preset.genres[0]) : null;
    if (tint) return tint;
    let hash = 0;
    for (const char of preset.name) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
    return PALETTE[hash % PALETTE.length];
  }
</script>

{#if presets.length > 0}
  <section class="flex flex-col gap-4" data-testid="preset-grid">
    <h2 class="text-2xl font-bold m-0">{$t('presets.title')}</h2>
    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
      {#each presets as preset (preset.id)}
        <button
          type="button"
          class="relative overflow-hidden rounded-lg h-24 p-3 border-none cursor-pointer text-left flex flex-col justify-between hover:brightness-110 active:scale-[0.98] transition"
          style="background-color: {colorFor(preset)}"
          onclick={() => onopen?.(preset)}
        >
          <!-- A MuMa tint can be as bright as the brand green; the wash keeps white text readable on any of them. -->
          <span class="absolute inset-0 bg-black/25" aria-hidden="true"></span>
          <span class="relative z-10 text-white font-bold text-sm leading-tight line-clamp-2">{preset.name}</span>
          <span class="relative z-10 text-white/70 text-[11px] truncate">{presetSummary(preset, $t)}</span>
          <svg viewBox="0 0 24 24" width="56" height="56" fill="white" class="absolute -right-3 -bottom-3 rotate-12 opacity-30" aria-hidden="true">
            {#if preset.sort === 'random'}
              <path d="M10.59 9.17L5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41l-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z"></path>
            {:else}
              <path d="M12 3v10.55A4 4 0 1 0 14 17V7h4V3h-6z"></path>
            {/if}
          </svg>
        </button>
      {/each}
    </div>
  </section>
{/if}
