<script>
  import { locale, t, SUPPORTED_LOCALES } from '../i18n/index.js';
  import { platform } from '../platform/index.js';

  /**
   * Sets the web UI's own language immediately, and tells the shell too -- fire-and-forget --
   * so native chrome (permission dialogs, share sheets) follows the pick
   * rather than staying on whatever locale the device booted with. A browser tab's `setAppLocale`
   * is a no-op; there is no native chrome there to begin with.
   */
  function pick(event) {
    const code = event.currentTarget.value;
    locale.set(code);
    platform.system.setAppLocale(code);
  }
</script>

<div class="flex items-center justify-between">
  <div class="flex flex-col gap-1">
    <h3 class="text-lg font-bold">{$t('settings.language.title')}</h3>
    <p class="text-sm text-[#b3b3b3]">{$t('settings.language.help')}</p>
  </div>
  <select
    aria-label={$t('settings.language.title')}
    value={$locale}
    onchange={pick}
    class="bg-[#282828] border border-white/10 rounded px-3 py-2 text-white focus:border-[#1DB954] focus:outline-none"
  >
    {#each SUPPORTED_LOCALES as { code, label } (code)}
      <option value={code}>{label}</option>
    {/each}
  </select>
</div>
