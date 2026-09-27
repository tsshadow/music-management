<script>
  import { t } from './i18n/index.js';
  import { onMount } from 'svelte';
  import { Settings2, CarFront, CircleHelp } from '@lucide/svelte';
  import { credentials, isAdmin, userPermissions, mumaUser, activeSettingsTab, flushFrontendSettings, resetSessionState, signedOut } from './store.js';
  import { platform } from './platform/index.js';
  import { logAction } from './diagnosticsLog.js';
  import Modal from './Modal.svelte';
  import { portal } from './portal.js';

  const { onNavigate } = $props();

  /** How long a logout waits for pending account-setting writes before it goes ahead anyway. */
  const LOGOUT_FLUSH_TIMEOUT_MS = 2000;

  /**
   * How long a logout waits for the phone's own sign-out. The bridge call used to crash on a
   * background thread and never answer, which left the button doing nothing at all (bug report
   * 106); a bound means a native failure can no longer hold the logout up.
   */
  const NATIVE_SIGN_OUT_TIMEOUT_MS = 5000;

  let isOpen = $state(false);
  /** Whether the "Log out?" confirmation is showing (issue #80, style guide: Session controls). */
  let confirmingLogout = $state(false);
  /** Set once the confirmed logout is running, so a second tap cannot start it twice. */
  let loggingOut = $state(false);
  const displayUsername = $derived($credentials.username || 'Gebruiker');

  /**
   * Toggles the visibility of the profile dropdown menu.
   *
   * @param {Event} event - The click event.
   */
  function toggleDropdown(event) {
    event.stopPropagation();
    isOpen = !isOpen;
  }

  /**
   * Logs out the user by clearing credentials and reloading the page.
   *
   * Awaits the phone's own sign-out first. Inside the Capacitor shell that clears the
   * credentials Kotlin has stored; skipping it -- or racing it with the reload -- was the bug:
   * `bootstrapShell()` read the untouched native credentials straight back out on the next boot
   * and signed the shell back in, so logging out visibly did nothing. A browser tab's
   * `signOut()` is a no-op that resolves at once, so this is unconditional rather than branching
   * on `platform.system.isNative`. The wait is bounded, and the `signedOut` marker makes the
   * next boot show the login page even when the phone could not be cleared (bug report 106).
   *
   * @param {Event} [event] - Optional click event.
   */
  async function handleLogout(event) {
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }

    logAction('auth.logout');

    try {
      await Promise.race([
        platform.system.signOut(),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('native sign-out timed out')), NATIVE_SIGN_OUT_TIMEOUT_MS),
        ),
      ]);
    } catch (error) {
      // Not fatal: `signedOut` below keeps the next boot from signing back in with whatever the
      // phone still holds, and asks the phone to forget it again then.
      console.warn("The native session could not be cleared before logging out", error);
    }

    // Whatever setting change is still on its debounce belongs to this account; write it
    // while the key still works. Bounded, so an unreachable server cannot hold the logout up.
    await Promise.race([
      flushFrontendSettings(),
      new Promise((resolve) => setTimeout(resolve, LOGOUT_FLUSH_TIMEOUT_MS)),
    ]);

    // Clear MuMa / Google session state, then everything else the account left behind: queue,
    // current track, player state, equalizer, page size, every account setting. See
    // `resetSessionState` in store.js -- it covers every persisted store, so none is forgotten.
    userPermissions.set([]);
    mumaUser.set(null);
    resetSessionState();
    // After the reset, which would otherwise not touch it anyway (a device store): the reload
    // below must land on the login page, not on a silent sign-in from the phone's copy.
    signedOut.set(true);

    isOpen = false;
    window.location.reload();
  }

  /**
   * Opens the logout confirmation instead of logging out at once. The style guide's Session
   * controls rule: a logout always confirms first and says what is lost and what is kept, so a
   * stray tap on the last menu row can no longer stop the music and empty the queue (issue #80).
   *
   * @param {Event} event - The click on the menu's "Log out" row.
   */
  function askLogout(event) {
    event.stopPropagation();
    isOpen = false;
    confirmingLogout = true;
  }

  /** Closes the confirmation and leaves the session exactly as it was. */
  function cancelLogout() {
    confirmingLogout = false;
  }

  /**
   * The confirmation's "Log out": runs the unchanged {@link handleLogout}. The dialog stays up
   * while the logout runs, since the page reloads at its end anyway.
   *
   * @param {Event} event - The click on the confirm button.
   */
  function confirmLogout(event) {
    if (loggingOut) return;
    loggingOut = true;
    handleLogout(event);
  }

  // Sluit dropdown bij klikken buiten
  /**
   * Closes the dropdown if a click occurs outside of the component.
   *
   * @param {Event} event - The click event.
   */
  function handleClickOutside(event) {
    if (isOpen && !event.target.closest('.profile-menu-container')) {
      isOpen = false;
    }
  }

  onMount(() => {
    window.addEventListener('click', handleClickOutside);

    return () => window.removeEventListener('click', handleClickOutside);
  });
</script>

<div class="relative profile-menu-container">
  <button
    class="flex items-center gap-2 bg-black/70 hover:bg-muma-spotify-light rounded-full p-0.5 md:pr-2 transition-colors cursor-pointer border-none text-white"
    onclick={toggleDropdown}
    aria-haspopup="true"
    aria-expanded={isOpen}
  >
    <div class="w-8 h-8 md:w-7 md:h-7 bg-muma-spotify-subtle rounded-full flex items-center justify-center overflow-hidden">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
        <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"></path>
      </svg>
    </div>
    <span class="text-sm font-bold hidden md:inline">{displayUsername}</span>
    <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" class="hidden md:block transition-transform {isOpen ? 'rotate-180' : ''}">
      <path d="M4 6l4 4 4-4"></path>
    </svg>
  </button>

  {#if isOpen}
    <div class="absolute right-0 mt-2 w-48 bg-muma-spotify-light rounded shadow-lg py-1 z-50">
      {#if $isAdmin}
        <button
          class="w-full text-left px-4 py-3 text-sm hover:bg-muma-spotify-highlight transition-colors border-none bg-transparent text-white cursor-pointer flex justify-between items-center"
          onclick={() => { isOpen = false; onNavigate('management'); }}
        >
          {$t('nav.management')}
          <Settings2 size={16} />
        </button>
      {/if}
      {#if platform.system.isNative}
        <button
          class="w-full text-left px-4 py-3 text-sm hover:bg-muma-spotify-highlight transition-colors border-none bg-transparent text-white cursor-pointer flex justify-between items-center"
          onclick={() => { isOpen = false; onNavigate('car'); }}
        >
          {$t('nav.carMode')}
          <CarFront size={16} />
        </button>
      {/if}
      <!-- The manual is a settings tab; opening it from here is the settings view with
           that tab already picked, so the phone (no sidebar) lands on the text, not on
           General. -->
      <button
        class="w-full text-left px-4 py-3 text-sm hover:bg-muma-spotify-highlight transition-colors border-none bg-transparent text-white cursor-pointer flex justify-between items-center"
        onclick={() => { isOpen = false; activeSettingsTab.set('help'); onNavigate('settings'); }}
      >
        {$t('nav.help')}
        <CircleHelp size={16} />
      </button>
      <button
        class="w-full text-left px-4 py-3 text-sm hover:bg-muma-spotify-highlight transition-colors border-none bg-transparent text-white cursor-pointer flex justify-between items-center"
        onclick={() => { isOpen = false; onNavigate('settings'); }}
      >
        {$t('common.settings')}
        <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
            <path d="M14 8.5V7.5H11.55C11.39 6.78 11.09 6.12 10.67 5.54L12.41 3.8L11.7 3.09L9.96 4.83C9.38 4.41 8.72 4.11 8 3.95V1.5H7V3.95C6.28 4.11 5.62 4.41 5.04 4.83L3.3 3.09L2.59 3.8L4.33 5.54C3.91 6.12 3.61 6.78 3.45 7.5H1V8.5H3.45C3.61 9.22 3.91 9.88 4.33 10.46L2.59 12.2L3.3 12.91L5.04 11.17C5.62 11.59 6.28 11.89 7 12.05V14.5H8V12.05C8.72 11.89 9.38 11.59 9.96 11.17L11.7 12.91L12.41 12.2L10.67 10.46C11.09 9.88 11.39 9.22 11.55 8.5H14ZM7.5 10C6.12 10 5 8.88 5 7.5C5 6.12 6.12 5 7.5 5C8.88 5 10 6.12 10 7.5C10 8.88 8.88 10 7.5 10Z"></path>
        </svg>
      </button>
      <div class="h-[1px] bg-muma-spotify-highlight mx-1 my-1"></div>
      <button
        class="w-full text-left px-4 py-3 text-sm hover:bg-muma-spotify-highlight transition-colors border-none bg-transparent text-white cursor-pointer"
        onclick={askLogout}
      >
        {$t('common.logout')}
      </button>
    </div>
  {/if}
</div>

{#if confirmingLogout}
  <!-- Portalled to <body>: both top bars are backdrop-blur-md, which would otherwise make the
       bar -- not the screen -- the box this fixed overlay fills. -->
  <div use:portal>
    <Modal title={$t('logout.confirmTitle')} onclose={cancelLogout} widthClass="max-w-md">
      <div class="flex flex-col gap-4" data-testid="logout-confirm">
        <p class="text-sm text-white m-0">{$t('logout.confirmLost')}</p>
        {#if platform.system.isNative}
          <!-- Only the phone keeps downloads; a browser tab has none to promise. -->
          <p class="text-sm text-muma-spotify-text m-0">{$t('logout.confirmKept')}</p>
        {/if}
        <div class="flex flex-wrap gap-3 justify-end">
          <button
            class="bg-transparent border border-muma-spotify-muted text-white px-6 py-2 rounded-[24px] font-bold cursor-pointer hover:border-white"
            onclick={cancelLogout}
          >{$t('common.cancel')}</button>
          <button
            class="bg-brand text-black px-6 py-2 rounded-[24px] font-bold cursor-pointer"
            data-testid="logout-confirm-button"
            disabled={loggingOut}
            onclick={confirmLogout}
          >{$t('common.logout')}</button>
        </div>
      </div>
    </Modal>
  </div>
{/if}
