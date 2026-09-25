<script>
  /**
   * Frame shared by the three edit pages: a way back to the thing being edited,
   * a title, and one place where errors and confirmations appear.
   *
   * The backend writes its 400s to be read by a person ("Genre 'Arts' has not been
   * accepted by curation"), so this shows `error` verbatim rather than replacing it
   * with a generic message.
   */
  import { ArrowLeft } from '@lucide/svelte';

  import { t } from '../i18n/index.js';

  let { title, subtitle = '', error = null, message = null, onback, children } = $props();
</script>

<div class="p-6 md:p-10 max-w-4xl mx-auto">
  <button
    class="flex items-center gap-2 text-muma-spotify-text hover:text-white bg-transparent border-none cursor-pointer p-0 mb-6"
    onclick={onback}
  >
    <ArrowLeft size={18} />
    <span class="text-sm font-bold">{$t('curation.back')}</span>
  </button>

  <h1 class="text-3xl md:text-5xl font-black m-0 leading-tight break-words">{title}</h1>
  {#if subtitle}
    <p class="text-muma-spotify-text text-sm mt-2 mb-0">{subtitle}</p>
  {/if}

  {#if error}
    <div class="mt-6 p-4 rounded bg-red-900/40 border border-red-700 text-sm" role="alert">{error}</div>
  {/if}
  {#if message}
    <div class="mt-6 p-4 rounded bg-muma-spotify-light text-sm" role="status">{message}</div>
  {/if}

  <div class="mt-8 flex flex-col gap-8">
    {@render children?.()}
  </div>
</div>
