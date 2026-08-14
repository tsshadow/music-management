<script>
  import { fly } from 'svelte/transition';
  import { AlertTriangle, CheckCircle2, Info, X, XCircle } from '@lucide/svelte';
  import { notifications, dismiss, dismissAll, pauseTimers, resumeTimers } from './notifications.js';
  import { isMobile } from './store.js';
  import { t } from './i18n/index.js';

  // Per type: the icon, the accent that carries the meaning at a glance, and
  // how urgently a screen reader should interrupt. Errors and warnings are
  // something the user has to react to; the other two are not.
  const VARIANTS = {
    error:   { Icon: XCircle,       accent: '#e22134', role: 'alert',  live: 'assertive' },
    warning: { Icon: AlertTriangle, accent: '#f0ad4e', role: 'alert',  live: 'assertive' },
    info:    { Icon: Info,          accent: '#b3b3b3', role: 'status', live: 'polite' },
    success: { Icon: CheckCircle2,  accent: '#1db954', role: 'status', live: 'polite' },
  };

  // Motion is decoration here; the notification still has to arrive for
  // someone who has asked the system for less of it.
  const reducedMotion =
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

  const flyIn = (node) => (reducedMotion ? { duration: 0 } : fly(node, { x: 24, duration: 200 }));
</script>

{#if $notifications.length > 0}
  <section
    class="fixed z-50 flex flex-col gap-2 {$isMobile
      ? 'top-18 left-4 right-4'
      : 'top-4 right-4 w-[380px] max-w-[calc(100vw-2rem)]'}"
    aria-label={$t('notify.region')}
    onmouseenter={pauseTimers}
    onmouseleave={resumeTimers}
    onfocusin={pauseTimers}
    onfocusout={resumeTimers}
  >
    {#each $notifications as item (item.id)}
      <!-- Destructured rather than used as `variant.Icon`: a member
           expression starting with a lowercase name is not usable as a
           component tag, and `<style.…>` would parse as a style element. -->
      {@const { Icon, accent, role, live } = VARIANTS[item.type]}
      <div
        class="flex items-start gap-3 rounded-md bg-[#282828] p-3 shadow-lg border-l-[3px]"
        style="border-left-color: {accent}"
        {role}
        aria-live={live}
        transition:flyIn
      >
        <Icon size={18} color={accent} class="mt-0.5 shrink-0" />
        <div class="min-w-0 flex-1">
          <p class="m-0 text-sm font-bold text-white break-words">{item.message}</p>
          {#if item.detail}
            <p class="m-0 mt-1 text-xs text-[#b3b3b3] break-words">{item.detail}</p>
          {/if}
        </div>
        {#if item.count > 1}
          <span class="shrink-0 rounded-full bg-[#3e3e3e] px-2 py-0.5 text-xs font-bold text-white">
            {item.count}&times;
          </span>
        {/if}
        <button
          class="shrink-0 cursor-pointer border-none bg-transparent p-0 text-[#b3b3b3] hover:text-white"
          aria-label={$t('notify.dismiss')}
          onclick={() => dismiss(item.id)}
        >
          <X size={16} />
        </button>
      </div>
    {/each}

    {#if $notifications.length > 1}
      <button
        class="self-end cursor-pointer border-none bg-transparent p-0 text-xs font-bold text-[#b3b3b3] hover:text-white"
        onclick={dismissAll}
      >
        {$t('notify.dismissAll')}
      </button>
    {/if}
  </section>
{/if}
