<script>
  import { t } from './i18n/index.js';
  import { equalizerSettings } from './store.js';
  import {
    EQ_FREQUENCIES,
    EQ_PRESETS,
    EQ_PRESET_NAMES,
    EQ_GAIN_MIN,
    EQ_GAIN_MAX,
    EQ_GAIN_STEP,
    CUSTOM_PRESET,
  } from './equalizerPresets.js';

  let { onclose = () => {} } = $props();

  const settings = $derived($equalizerSettings);

  /** 1000 -> "1k", so ten labels fit under ten sliders on a phone. */
  function labelFor(frequency) {
    return frequency >= 1000 ? `${frequency / 1000}k` : String(frequency);
  }

  function formatDb(value) {
    const rounded = Math.round(value * 10) / 10;
    return `${rounded > 0 ? '+' : ''}${rounded} dB`;
  }

  function toggleEnabled() {
    equalizerSettings.update((s) => ({ ...s, enabled: !s.enabled }));
  }

  function choosePreset(name) {
    const preset = EQ_PRESETS[name];
    if (!preset) return;
    equalizerSettings.update((s) => ({
      ...s,
      preset: name,
      gains: preset.gains.slice(),
      preamp: preset.preamp,
    }));
  }

  /**
   * Moving a band by hand no longer matches the named curve, so the picker
   * drops to "custom" rather than lying about which preset is active.
   */
  function changeBand(index, value) {
    const gain = Number(value);
    equalizerSettings.update((s) => {
      const gains = s.gains.slice();
      gains[index] = gain;
      return { ...s, gains, preset: CUSTOM_PRESET };
    });
  }

  function changePreamp(value) {
    equalizerSettings.update((s) => ({ ...s, preamp: Number(value) }));
  }

  function reset() {
    equalizerSettings.update((s) => ({
      ...s,
      gains: EQ_FREQUENCIES.map(() => 0),
      preamp: 0,
      preset: 'flat',
    }));
  }

  function onKeyDown(event) {
    if (event.key === 'Escape') onclose();
  }
</script>

<svelte:window onkeydown={onKeyDown} />

<div
  class="bg-muma-spotify-panel border border-white/10 rounded-lg shadow-2xl p-4 w-[340px] max-w-[92vw] text-white"
  role="dialog"
  aria-label={$t('equalizer.title')}
>
  <div class="flex items-center justify-between mb-3">
    <h2 class="text-sm font-bold">{$t('equalizer.title')}</h2>
    <div class="flex items-center gap-3">
      <label class="relative inline-flex items-center cursor-pointer">
        <input
          type="checkbox"
          class="sr-only peer"
          checked={settings.enabled}
          onchange={toggleEnabled}
          aria-label={$t('equalizer.enabled')}
        />
        <div class="w-9 h-5 bg-[#4d4d4d] rounded-full peer-checked:bg-brand transition-colors"></div>
        <div class="absolute left-0.5 w-4 h-4 bg-white rounded-full transition-transform peer-checked:translate-x-4"></div>
      </label>
      <button
        class="bg-transparent border-none p-0 text-muma-spotify-text hover:text-white cursor-pointer"
        onclick={onclose}
        aria-label={$t('equalizer.close')}
      >
        <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor" aria-hidden="true">
          <path d="M2.47 2.47a.75.75 0 0 1 1.06 0L8 6.94l4.47-4.47a.75.75 0 1 1 1.06 1.06L9.06 8l4.47 4.47a.75.75 0 1 1-1.06 1.06L8 9.06l-4.47 4.47a.75.75 0 0 1-1.06-1.06L6.94 8 2.47 3.53a.75.75 0 0 1 0-1.06z"></path>
        </svg>
      </button>
    </div>
  </div>

  <div class="flex flex-col gap-1 mb-4" class:opacity-40={!settings.enabled}>
    <label class="text-[11px] uppercase tracking-wider text-muma-spotify-text" for="eq-preset">
      {$t('equalizer.preset')}
    </label>
    <select
      id="eq-preset"
      class="bg-muma-spotify-light text-white text-sm px-3 py-1.5 rounded border border-white/10 outline-none focus:border-brand"
      value={settings.preset}
      onchange={(e) => choosePreset(e.currentTarget.value)}
      aria-label={$t('equalizer.preset')}
    >
      {#if settings.preset === CUSTOM_PRESET}
        <option value={CUSTOM_PRESET}>{$t('equalizer.presets.custom')}</option>
      {/if}
      {#each EQ_PRESET_NAMES as name (name)}
        <option value={name}>{$t(`equalizer.presets.${name}`)}</option>
      {/each}
    </select>
  </div>

  <div class="flex items-end justify-between gap-1 mb-3" class:opacity-40={!settings.enabled}>
    {#each EQ_FREQUENCIES as frequency, index (frequency)}
      <div class="flex flex-col items-center gap-1 flex-1">
        <span class="text-[9px] text-muma-spotify-text tabular-nums">{formatDb(settings.gains[index])}</span>
        <input
          type="range"
          class="eq-slider accent-brand"
          min={EQ_GAIN_MIN}
          max={EQ_GAIN_MAX}
          step={EQ_GAIN_STEP}
          value={settings.gains[index]}
          oninput={(e) => changeBand(index, e.currentTarget.value)}
          aria-label={$t('equalizer.band', { freq: labelFor(frequency) })}
        />
        <span class="text-[9px] text-muma-spotify-text">{labelFor(frequency)}</span>
      </div>
    {/each}
  </div>

  <div class="flex items-center gap-3 pt-3 border-t border-white/5" class:opacity-40={!settings.enabled}>
    <label class="text-[11px] uppercase tracking-wider text-muma-spotify-text w-20" for="eq-preamp">
      {$t('equalizer.preamp')}
    </label>
    <input
      id="eq-preamp"
      type="range"
      class="flex-1 accent-brand"
      min={EQ_GAIN_MIN}
      max={EQ_GAIN_MAX}
      step={EQ_GAIN_STEP}
      value={settings.preamp}
      oninput={(e) => changePreamp(e.currentTarget.value)}
      aria-label={$t('equalizer.preamp')}
    />
    <span class="text-[10px] text-muma-spotify-text w-14 text-right tabular-nums">{formatDb(settings.preamp)}</span>
  </div>

  <button
    class="mt-3 w-full bg-muma-spotify-light hover:bg-muma-spotify-highlight text-white text-xs font-bold py-2 rounded border-none cursor-pointer transition-colors"
    onclick={reset}
  >
    {$t('equalizer.reset')}
  </button>
</div>

<style>
  /* Vertical sliders: the band controls only read as an equalizer standing up. */
  .eq-slider {
    writing-mode: vertical-lr;
    direction: rtl;
    width: 14px;
    height: 96px;
  }
</style>
