<script>
  /**
   * Correcting a track's tempo by hand: halve it, double it, type a value, or go back to the
   * measured tempo once it has been set by hand.
   *
   * Only shown to a user with the `bpm.override` permission, and only when the caller knows the
   * library track id (MuMa's, not LMS's song id). The answer from MuMa is handed to `onchange`
   * as the BPM fields to merge into whatever the caller shows -- the inspector's track, the list
   * row, the details sheet's tag rows -- so this component owns no copy of the track.
   *
   * Built only from existing tokens (docs/styleguide.md, "Correct a BPM by hand"): the secondary
   * pills of the track inspector, a Forms & Inputs field, and a red error line.
   *
   * @typedef {Object} Props
   * @property {number|null} trackId - The library track id; nothing renders without one.
   * @property {number|null} [bpm] - The tempo shown now; halving and doubling need one.
   * @property {string|null} [source] - `bpm_source`; "Measured" is offered only for `manual`.
   * @property {function(Object): void} [onchange] - Receives `overrideFields(answer)`.
   */
  import { t } from './i18n/index.js';
  import { hasPermission, mumaUser, userPermissions } from './store.js';
  import {
    OVERRIDE_PERMISSION,
    clearManualBpm,
    overrideErrorDetail,
    overrideFields,
    parseBpm,
    setManualBpm,
  } from './bpm.js';

  /** @type {Props} */
  let { trackId, bpm = null, source = null, onchange } = $props();

  // Read both stores so a sign-in or a role change re-evaluates the permission.
  const allowed = $derived.by(() => {
    void $userPermissions;
    void $mumaUser;
    return hasPermission(OVERRIDE_PERMISSION);
  });
  const hasBpm = $derived(bpm !== null && bpm !== undefined && Number(bpm) > 0);

  let typed = $state('');
  let busy = $state(false);
  let error = $state('');

  // Another track on screen: its own field and no leftover error from the previous one.
  $effect(() => {
    void trackId;
    typed = '';
    error = '';
  });

  const PILL =
    'text-xs font-bold bg-white/5 hover:bg-white/10 border border-white/10 rounded-full px-3 min-h-8 transition-colors disabled:opacity-50 disabled:cursor-not-allowed';

  /**
   * Run one override request and report its answer, or show why it failed.
   *
   * @param {() => Promise<Object>} request
   */
  async function run(request) {
    busy = true;
    error = '';
    try {
      const answer = await request();
      typed = '';
      onchange?.(overrideFields(answer));
    } catch (err) {
      error = overrideErrorDetail(err) ?? $t('bpm.override.failed');
    } finally {
      busy = false;
    }
  }

  /**
   * Halve or double the tempo shown now.
   *
   * @param {number} factor
   */
  function scale(factor) {
    run(() => setManualBpm(trackId, { factor }));
  }

  /**
   * Set the typed tempo, after checking it is one MuMa accepts.
   *
   * @param {SubmitEvent} event
   */
  function submit(event) {
    event.preventDefault();
    const value = parseBpm(typed);
    if (value === null) {
      error = $t('bpm.override.invalid');
      return;
    }
    run(() => setManualBpm(trackId, { bpm: value }));
  }

  /** Back to the measured tempo. */
  function reset() {
    run(() => clearManualBpm(trackId));
  }
</script>

{#if allowed && trackId !== null && trackId !== undefined}
  <div class="flex flex-col gap-2" data-testid="bpm-override">
    <span class="text-[9px] uppercase tracking-widest text-muma-spotify-text">{$t('bpm.override.title')}</span>
    <div class="flex flex-wrap items-center gap-2">
      <button
        type="button"
        class={PILL}
        aria-label={$t('bpm.override.halveLabel')}
        title={$t('bpm.override.halveLabel')}
        disabled={busy || !hasBpm}
        onclick={() => scale(0.5)}
      >{$t('bpm.override.halve')}</button>
      <button
        type="button"
        class={PILL}
        aria-label={$t('bpm.override.doubleLabel')}
        title={$t('bpm.override.doubleLabel')}
        disabled={busy || !hasBpm}
        onclick={() => scale(2)}
      >{$t('bpm.override.double')}</button>
      {#if source === 'manual'}
        <button
          type="button"
          class={PILL}
          title={$t('bpm.override.resetLabel')}
          disabled={busy}
          onclick={reset}
        >{$t('bpm.override.reset')}</button>
      {/if}
    </div>
    <form class="flex items-center gap-2" onsubmit={submit}>
      <input
        type="text"
        inputmode="decimal"
        class="w-20 min-h-8 bg-muma-spotify-light border border-white/10 rounded px-2 text-xs text-white font-mono tabular-nums focus:outline-none focus:border-brand disabled:opacity-50"
        aria-label={$t('bpm.override.inputLabel')}
        placeholder="BPM"
        bind:value={typed}
        disabled={busy}
      />
      <button type="submit" class={PILL} disabled={busy}>{$t('bpm.override.set')}</button>
    </form>
    {#if error}
      <p class="text-xs text-red-400 m-0" role="alert" data-testid="bpm-override-error">{error}</p>
    {/if}
  </div>
{/if}
