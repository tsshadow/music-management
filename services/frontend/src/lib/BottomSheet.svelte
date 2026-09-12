<script>
  import { t } from './i18n/index.js';
  import { onMount, onDestroy } from 'svelte';
  import { fly, fade } from 'svelte/transition';

  /**
   * A mobile bottom sheet: a dark panel that slides up from the bottom of the
   * screen, used instead of a `<select>` for the phone-sized filter chips
   * (`FilterBar`, `CollectionBar`). No dependency beyond Svelte itself --
   * `Modal.svelte` is the desktop/shared equivalent this deliberately mirrors
   * (backdrop click, Escape, a body-scroll lock while it is open) but a sheet
   * anchors to the bottom edge and carries a drag handle instead of a
   * centered dialog.
   *
   * Rendered conditionally by the caller, the same way `Modal` is -- there is
   * no internal `open` flag, so mounting *is* opening and calling `onclose`
   * is what the caller reacts to by unmounting it.
   *
   * The slide/fade below is `in:` only, not `transition:` (which would also
   * play on the way out). jsdom's `element.animate()` shim in the test setup
   * is enough for an *intro* to render, but an *outro* never resolves there,
   * which left the sheet stuck in the DOM after every close in a test --
   * closing for real users, just not observably so under jsdom.
   *
   * @typedef {Object} Props
   * @property {string} [title] - Sheet title, shown in the header.
   * @property {function(): void} onclose - Callback invoked to close the sheet.
   * @property {import('svelte').Snippet} [children] - Sheet content (usually a list of options).
   */

  /** @type {Props} */
  let { title = '', onclose, children } = $props();

  let sheetEl = $state(null);

  function handleKeydown(e) {
    if (e.key === 'Escape') {
      onclose();
      return;
    }
    if (e.key === 'Tab' && sheetEl) {
      // A focus trap: Tab out of either end of the sheet wraps to the other
      // end rather than escaping to whatever the sheet is covering.
      const focusable = sheetEl.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  onMount(() => {
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', handleKeydown);
    // Land focus inside the sheet so Tab/Escape work immediately, without
    // stealing it from a field the caller cares about restoring later.
    const focusable = sheetEl?.querySelector(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    (focusable ?? sheetEl)?.focus();
  });

  onDestroy(() => {
    document.body.style.overflow = '';
    window.removeEventListener('keydown', handleKeydown);
  });
</script>

<div class="fixed inset-0 z-[100] flex items-end justify-center" data-testid="bottom-sheet">
  <!-- Backdrop -->
  <button
    class="absolute inset-0 bg-black/70 w-full h-full cursor-default border-none"
    onclick={onclose}
    aria-label={$t('common.closeSheet')}
    in:fade={{ duration: 150 }}
  ></button>

  <!-- Sheet -->
  <div
    bind:this={sheetEl}
    role="dialog"
    aria-modal="true"
    aria-label={title}
    tabindex="-1"
    class="relative w-full max-h-[80vh] bg-[#181818] rounded-t-2xl shadow-2xl flex flex-col overflow-hidden border-t border-white/10 outline-none"
    in:fly={{ y: 300, duration: 200 }}
  >
    <!-- Grip -->
    <div class="flex justify-center pt-2 pb-1 shrink-0" aria-hidden="true">
      <div class="w-9 h-1 rounded-full bg-white/20"></div>
    </div>

    {#if title}
      <div class="flex items-center justify-between px-4 pb-2 shrink-0">
        <h2 class="text-base font-bold m-0 text-white">{title}</h2>
        <button
          class="text-[#b3b3b3] hover:text-white transition-colors bg-transparent border-none p-1 cursor-pointer"
          onclick={onclose}
          aria-label={$t('common.close')}
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <path d="M18.3 5.71a.996.996 0 00-1.41 0L12 10.59 7.11 5.7a.996.996 0 10-1.41 1.41L10.59 12 5.7 16.89a.996.996 0 101.41 1.41L12 13.41l4.89 4.89a.996.996 0 101.41-1.41L13.41 12l4.89-4.89c.38-.38.38-1.02 0-1.4z"/>
          </svg>
        </button>
      </div>
    {/if}

    <div class="flex-1 overflow-y-auto pb-[env(safe-area-inset-bottom)]">
      {#if children}
        {@render children()}
      {/if}
    </div>
  </div>
</div>
