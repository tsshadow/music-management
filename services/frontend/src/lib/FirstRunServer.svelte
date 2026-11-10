<script>
  /**
   * The first-run server screen (issue #192, docs/designs/first-run-server/): asks the address of
   * the listener's MuMa server, has the phone check it, and hands a checked address to
   * `onconfirm`. Shown by the Android shell instead of the login page while no address is stored,
   * from the login page's "Wijzigen" link, and from Settings > Apparaat to change the server.
   *
   * Laid out like the login page (style guide: "First-run server screen"). The check is native
   * (`platform.system.checkServerAddress`); this screen only words its answer. Only `ok` goes on
   * by itself; `mumaUnreachable` goes on with "Toch doorgaan", every other state stays.
   */
  import { onMount } from 'svelte';
  import { t } from './i18n/index.js';
  import MumaMark from './MumaMark.svelte';
  import Throbber from './loading/Throbber.svelte';
  import { platform as defaultPlatform } from './platform/index.js';

  /**
   * @type {{
   *   mode?: 'first'|'change',
   *   current?: string,
   *   onconfirm: (check: import('./platform/index.js').ServerAddressCheck) => Promise<void>,
   *   oncancel?: () => void,
   *   platform?: object,
   * }}
   */
  const { mode = 'first', current = '', onconfirm, oncancel = undefined, platform = defaultPlatform } = $props();

  /** The example under the field. Not translated: it is an address, and the smoke test looks for it. */
  const EXAMPLE = 'https://music.example.net';

  let address = $state('');
  let busy = $state(false);
  /** @type {import('./platform/index.js').ServerAddressCheck|null} */
  let check = $state(null);
  let saveError = $state('');

  const message = $derived(
    check && check.state !== 'ok' ? $t(`firstRun.state.${check.state}`, { url: check.url || address.trim() }) : '',
  );

  onMount(async () => {
    // A change starts from the address in use; a first run from the build's own server, if any.
    if (current) {
      address = current;
      return;
    }
    if (mode !== 'first') return;
    const suggestion = await platform.system.suggestedServerAddress();
    // Never over what the listener already started typing.
    if (!address) address = suggestion;
  });

  /** Asks the phone whether a MuMa server answers at the typed address; goes on when one does. */
  async function connect() {
    if (busy) return;
    saveError = '';
    check = null;
    busy = true;
    try {
      check = await platform.system.checkServerAddress(address.trim());
    } catch (error) {
      console.warn('The server check could not run', error);
      check = { state: 'unreachable', url: address.trim(), subsonic: '', mumaApi: '', buildServer: false };
    }
    busy = false;
    if (check.state === 'ok') await confirm();
  }

  /** Hands the checked address on; a failure to store it is shown, and the screen stays. */
  async function confirm() {
    if (!check?.url) return;
    busy = true;
    try {
      await onconfirm(check);
    } catch (error) {
      saveError = $t('firstRun.saveFailed', { reason: error?.message || error?.code || '?' });
    }
    busy = false;
  }
</script>

<div class="min-h-screen w-screen bg-black flex flex-col justify-center items-center p-4 text-white" data-testid="first-run-server">
  <div class="bg-muma-spotify-panel border border-muma-spotify-light p-10 rounded-2xl w-full max-w-md flex flex-col gap-6 shadow-2xl">
    <div class="flex flex-col items-center gap-2 mb-2">
      <div class="w-14 h-14 bg-brand rounded-full flex items-center justify-center text-black mb-1">
        <MumaMark size={32} />
      </div>
      <h1 class="text-3xl font-extrabold tracking-tight m-0">MuMa</h1>
      <h2 class="text-sm font-medium text-muma-spotify-text m-0 text-center">
        {mode === 'change' ? $t('firstRun.changeTitle') : $t('firstRun.title')}
      </h2>
    </div>

    <p class="text-sm text-muma-spotify-text text-center m-0">{$t('firstRun.intro')}</p>

    {#if message || saveError}
      <div class="bg-[#e91429] text-white p-3 rounded-lg text-sm font-medium" role="alert">{saveError || message}</div>
    {/if}

    <!-- novalidate: a `type="url"` field refuses `music.example.net`, which the phone reads as https. -->
    <form class="flex flex-col gap-2" novalidate onsubmit={(e) => { e.preventDefault(); connect(); }}>
      <label for="server-address" class="text-xs font-bold text-muma-spotify-text uppercase tracking-wider">{$t('firstRun.label')}</label>
      <input
        id="server-address"
        type="url"
        inputmode="url"
        autocomplete="url"
        autocapitalize="off"
        spellcheck="false"
        value={address}
        oninput={(e) => { address = e.target.value; check = null; saveError = ''; }}
        placeholder={EXAMPLE}
        class="bg-[#2a2a2a] border border-transparent rounded-lg p-3 text-white text-sm focus:outline-none focus:border-brand-green disabled:opacity-50"
        disabled={busy}
      />
      <p class="text-[11px] text-muma-spotify-text m-0">{$t('firstRun.example')} <span>{EXAMPLE}</span></p>
      {#if busy}
        <p class="flex items-center gap-2 text-xs text-muma-spotify-text m-0"><Throbber size={14} /> {$t('firstRun.checking')}</p>
      {/if}
      <button type="submit" class="flex items-center justify-center gap-2 bg-brand-green hover:bg-[#1ed760] text-black border-none rounded-full p-3.5 text-base font-extrabold cursor-pointer transition-transform hover:scale-[1.02] disabled:opacity-50 mt-2" disabled={busy || !address.trim()}>
        {#if busy}<Throbber size={18} />{/if}
        {$t('firstRun.connect')}
      </button>
    </form>

    {#if check?.state === 'mumaUnreachable'}
      <button type="button" class="bg-muma-spotify-hover hover:bg-[#444] text-white font-bold py-2 px-6 rounded-full border-none cursor-pointer disabled:opacity-50" onclick={confirm} disabled={busy}>
        {$t('firstRun.continueAnyway')}
      </button>
    {:else if check?.state === 'noNetwork'}
      <button type="button" class="bg-muma-spotify-hover hover:bg-[#444] text-white font-bold py-2 px-6 rounded-full border-none cursor-pointer disabled:opacity-50" onclick={connect} disabled={busy}>
        {$t('firstRun.retry')}
      </button>
    {/if}

    {#if oncancel}
      <button type="button" class="text-muma-spotify-text text-sm hover:underline bg-transparent border-none cursor-pointer" onclick={oncancel} disabled={busy}>{$t('firstRun.cancel')}</button>
    {/if}
  </div>
</div>
