<script>
  import { t } from './i18n/index.js';
  import { platform as defaultPlatform } from './platform/index.js';
  import { safeSourceUrl } from './sourceLink.js';

  /**
   * The small "Source code" link on the login screen: the AGPL-3.0 section 13 offer has to reach
   * people before they sign in. Secondary text, underlined on hover, like the other quiet links.
   * Renders nothing without a safe http(s) address. In the app the link goes through the shell to
   * the system browser instead of navigating the WebView away.
   *
   * @typedef {Object} Props
   * @property {string} [url] - The address the server reported.
   * @property {Object} [platform] - The platform shim.
   */
  /** @type {Props} */
  const { url = '', platform = defaultPlatform } = $props();

  const href = $derived(safeSourceUrl(url));

  /** @param {MouseEvent} event */
  function open(event) {
    if (platform?.system?.isNative !== true) return;
    event.preventDefault();
    platform.system.openUrl(href).catch((e) => console.warn('Could not open the source code link', e));
  }
</script>

{#if href}
  <a
    {href}
    target="_blank"
    rel="noopener noreferrer"
    class="text-xs text-muma-spotify-text hover:text-white hover:underline text-center"
    data-testid="source-link"
    onclick={open}
  >{$t('settings.about.sourceCode')}</a>
{/if}
