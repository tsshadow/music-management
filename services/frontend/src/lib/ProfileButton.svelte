<script>
  import { t } from './i18n/index.js';
  import { onMount } from 'svelte';
  import { Settings2 } from '@lucide/svelte';
  import { credentials, isAdmin, mumaApiKey, mumaRefreshToken, mumaSessionActive, userPermissions, mumaUser, defaultSubsonicUrl } from './store.js';
  import { platform } from './platform/index.js';
  import { logAction } from './diagnosticsLog.js';

  const { onNavigate } = $props();

  let isOpen = $state(false);
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
   * on `platform.system.isNative`.
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
      await platform.system.signOut();
    } catch (error) {
      console.warn("The native session could not be cleared before logging out", error);
    }

    // Reset credentials and ensure localStorage is updated
    const emptyCreds = { url: defaultSubsonicUrl(), username: '', password: '' };
    credentials.set(emptyCreds);
    localStorage.setItem('lms_credentials', JSON.stringify(emptyCreds));

    // Clear MuMa / Google session state and localStorage
    mumaApiKey.set('');
    localStorage.setItem('muma_api_key', JSON.stringify(''));
    mumaRefreshToken.set('');
    localStorage.setItem('muma_refresh_token', JSON.stringify(''));
    mumaSessionActive.set(false);
    localStorage.setItem('muma_session_active', JSON.stringify(false));
    userPermissions.set([]);
    mumaUser.set(null);

    // Clear view state to return to home on next login
    localStorage.removeItem('lms_active_view');

    isOpen = false;
    window.location.reload();
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
    class="flex items-center gap-2 bg-black/70 hover:bg-[#282828] rounded-full p-0.5 pr-2 transition-colors cursor-pointer border-none text-white"
    onclick={toggleDropdown}
    aria-haspopup="true"
    aria-expanded={isOpen}
  >
    <div class="w-7 h-7 bg-[#535353] rounded-full flex items-center justify-center overflow-hidden">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
        <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"></path>
      </svg>
    </div>
    <span class="text-sm font-bold hidden md:inline">{displayUsername}</span>
    <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" class="transition-transform {isOpen ? 'rotate-180' : ''}">
      <path d="M4 6l4 4 4-4"></path>
    </svg>
  </button>

  {#if isOpen}
    <div class="absolute right-0 mt-2 w-48 bg-[#282828] rounded shadow-lg py-1 z-50">
      {#if $isAdmin}
        <button
          class="w-full text-left px-4 py-3 text-sm hover:bg-[#3e3e3e] transition-colors border-none bg-transparent text-white cursor-pointer flex justify-between items-center"
          onclick={() => { isOpen = false; onNavigate('management'); }}
        >
          {$t('nav.management')}
          <Settings2 size={16} />
        </button>
      {/if}
      <button
        class="w-full text-left px-4 py-3 text-sm hover:bg-[#3e3e3e] transition-colors border-none bg-transparent text-white cursor-pointer flex justify-between items-center"
        onclick={() => { isOpen = false; onNavigate('settings'); }}
      >
        {$t('common.settings')}
        <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
            <path d="M14 8.5V7.5H11.55C11.39 6.78 11.09 6.12 10.67 5.54L12.41 3.8L11.7 3.09L9.96 4.83C9.38 4.41 8.72 4.11 8 3.95V1.5H7V3.95C6.28 4.11 5.62 4.41 5.04 4.83L3.3 3.09L2.59 3.8L4.33 5.54C3.91 6.12 3.61 6.78 3.45 7.5H1V8.5H3.45C3.61 9.22 3.91 9.88 4.33 10.46L2.59 12.2L3.3 12.91L5.04 11.17C5.62 11.59 6.28 11.89 7 12.05V14.5H8V12.05C8.72 11.89 9.38 11.59 9.96 11.17L11.7 12.91L12.41 12.2L10.67 10.46C11.09 9.88 11.39 9.22 11.55 8.5H14ZM7.5 10C6.12 10 5 8.88 5 7.5C5 6.12 6.12 5 7.5 5C8.88 5 10 6.12 10 7.5C10 8.88 8.88 10 7.5 10Z"></path>
        </svg>
      </button>
      <div class="h-[1px] bg-[#3e3e3e] mx-1 my-1"></div>
      <button
        class="w-full text-left px-4 py-3 text-sm hover:bg-[#3e3e3e] transition-colors border-none bg-transparent text-white cursor-pointer"
        onclick={handleLogout}
      >
        {$t('common.logout')}
      </button>
    </div>
  {/if}
</div>
