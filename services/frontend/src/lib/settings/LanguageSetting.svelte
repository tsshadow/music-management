<script>
  import { locale, t, SUPPORTED_LOCALES } from '../i18n/index.js';
  import { platform } from '../platform/index.js';
  import { flushLocaleSave } from '../store.js';

  /**
   * Sets the web UI's own language immediately, and tells the shell too, so native chrome
   * (permission dialogs, share sheets) follows the pick rather than staying on whatever locale
   * the device booted with. A browser tab's `setAppLocale` is a no-op; there is no native chrome
   * there to begin with.
   *
   * The shell applies the language by recreating its activity, which reloads the WebView. The
   * account must hold the new language before that happens: the reload re-applies whatever the
   * account says, and the debounced save would otherwise die with the page -- the pick then looks
   * like a refresh that changed nothing.
   */
  async function pick(event) {
    const code = event.currentTarget.value;
    locale.set(code);
    await flushLocaleSave();
    platform.system.setAppLocale(code);
  }
</script>

<div class="flex items-center justify-between">
  <div class="flex flex-col gap-1">
    <h3 class="text-lg font-bold">{$t('settings.language.title')}</h3>
    <p class="text-sm text-muma-spotify-text">{$t('settings.language.help')}</p>
  </div>
  <select
    aria-label={$t('settings.language.title')}
    value={$locale}
    onchange={pick}
    class="bg-muma-spotify-light border border-white/10 rounded px-3 py-2 text-white focus:border-brand-green focus:outline-none"
  >
    {#each SUPPORTED_LOCALES as { code, label } (code)}
      <option value={code}>{label}</option>
    {/each}
  </select>
</div>
