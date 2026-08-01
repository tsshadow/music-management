<script>
  import { t } from '../i18n/index.js';
  import { visibleSortOptions, allSortOptions, authParams, credentials } from '../store.js';

  let newPassword = $state('');
  let confirmPassword = $state('');
  let passwordMessage = $state('');
  let passwordError = $state(false);
  let isChangingPassword = $state(false);

  async function changePassword() {
    if (newPassword !== confirmPassword) {
      passwordMessage = $t('settings.advanced.passwordMismatch');
      passwordError = true;
      return;
    }
    if (newPassword.length < 4) {
      passwordMessage = $t('settings.advanced.passwordTooShort');
      passwordError = true;
      return;
    }

    isChangingPassword = true;
    passwordMessage = '';
    try {
      const resp = await fetch(`/rest/updateUser?${$authParams}&username=${encodeURIComponent($credentials.username)}&password=${encodeURIComponent(newPassword)}`);
      const data = await resp.json();
      if (data['subsonic-response']?.status === 'ok') {
        passwordMessage = $t('settings.advanced.passwordChanged');
        passwordError = false;
        newPassword = '';
        confirmPassword = '';
      } else {
        passwordMessage = $t('settings.advanced.passwordFailed');
        passwordError = true;
      }
    } catch {
      passwordMessage = 'Netwerkfout';
      passwordError = true;
    } finally {
      isChangingPassword = false;
    }
  }

  /**
   * Toggles the visibility of a specific sort option for a given type.
   */
  function toggleOption(type, id) {
    visibleSortOptions.update(options => {
      const current = options[type];
      if (current.includes(id)) {
        options[type] = current.filter(i => i !== id);
      } else {
        options[type] = [...current, id];
      }
      return options;
    });
  }
</script>

<div class="max-w-4xl pb-24">
  <header class="mb-8">
    <h1 class="text-3xl font-bold mb-2">{$t('settings.advanced.title')}</h1>
    <p class="text-[#b3b3b3]">{$t('settings.advanced.subtitle')}</p>
  </header>

  <div class="flex flex-col gap-8">
    <!-- Security Section -->
    <section class="bg-[#181818] rounded-lg p-6 shadow-lg border border-white/5">
      <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.advanced.security')}</h2>

      <div>
        <h3 class="text-lg font-bold mb-4">{$t('settings.advanced.changePassword')}</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-2xl">
          <div class="flex flex-col gap-2">
            <label for="new-password" class="text-xs font-bold text-[#b3b3b3] uppercase">{$t('settings.advanced.newPassword')}</label>
            <input
              id="new-password"
              type="password"
              bind:value={newPassword}
              class="bg-[#282828] text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand"
            />
          </div>
          <div class="flex flex-col gap-2">
            <label for="confirm-password" class="text-xs font-bold text-[#b3b3b3] uppercase">{$t('settings.advanced.confirmPassword')}</label>
            <input
              id="confirm-password"
              type="password"
              bind:value={confirmPassword}
              class="bg-[#282828] text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand"
            />
          </div>
        </div>
        <button
          onclick={changePassword}
          disabled={isChangingPassword || !newPassword}
          class="mt-6 bg-[#333] hover:bg-[#444] text-white font-bold py-2 px-8 rounded-full transition-colors disabled:opacity-50"
        >
          {isChangingPassword ? $t('settings.advanced.changing') : $t('settings.advanced.updatePassword')}
        </button>
        {#if passwordMessage}
          <p class="mt-2 text-sm {passwordError ? 'text-red-500' : 'text-brand'}">{passwordMessage}</p>
        {/if}
      </div>
    </section>

    <!-- Sort Options -->
    <section class="bg-[#181818] rounded-lg p-6 shadow-lg border border-white/5">
      <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">{$t('settings.advanced.sortOptions')}</h2>
      <p class="text-[#b3b3b3] mb-8 text-sm">{$t('settings.advanced.sortOptionsHelp')}</p>

      <div class="flex flex-col gap-8">
        {#each Object.entries(allSortOptions) as [type, options] (type)}
          <div>
            <h4 class="text-sm font-bold text-[#b3b3b3] uppercase tracking-wider mb-4">
              {type === 'songs' ? 'Nummers' : type === 'albums' ? 'Albums' : 'Artiesten'}
            </h4>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
              {#each options as option (option.id)}
                <label class="flex items-center gap-3 p-3 bg-[#282828] rounded-md border border-transparent hover:border-[#3e3e3e] cursor-pointer transition-colors">
                  <input
                    type="checkbox"
                    class="w-5 h-5 accent-brand"
                    checked={$visibleSortOptions[type].includes(option.id)}
                    onchange={() => toggleOption(type, option.id)}
                  />
                  <span class="text-white font-medium">{$t(option.labelKey)}</span>
                </label>
              {/each}
            </div>
          </div>
        {/each}
      </div>
    </section>
  </div>
</div>

<style>
  .text-brand { color: #1ed760; }
</style>
