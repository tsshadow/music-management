<script>
  import { onMount } from 'svelte';
  import ProfileButton from './ProfileButton.svelte';
  import SearchBar from './SearchBar.svelte';
  import ReleaseNotesModal from './ReleaseNotesModal.svelte';
  import { activeView, authParams, activeModal, sidebarDrawerOpen } from './store.js';
  import { t } from './i18n/index.js';
  import { Menu } from '@lucide/svelte';
  import { get } from 'svelte/store';

  const { greeting = "" } = $props();

  // The bottom bar covers the player views, but it has no entry for the
  // settings and management tabs -- those only live in the sidebar, which is
  // hidden below `md`. So on those two views the top bar carries the opener.
  const hasDrawer = $derived($activeView === 'settings' || $activeView === 'management');

  async function checkVersion() {
      try {
          const auth = get(authParams);
          if (!auth) return;

          const response = await fetch(`/rest/ping?${auth}`);
          const data = await response.json();
          const res = data['subsonic-response'];
          if (!res) return;

          const currentVersion = res.serverVersion || res.version;
          const lastVersion = localStorage.getItem('lms_last_version');

          if (lastVersion && lastVersion !== currentVersion) {
              const rnResponse = await fetch('/release-notes.json');
              if (rnResponse.ok) {
                  const releases = await rnResponse.json();
                  const newReleases = releases.filter(r => isNewer(r.version, lastVersion));
                  if (newReleases.length > 0) {
                      activeModal.set({ type: 'release-notes', data: { releases: newReleases } });
                  }
              }
          }
          localStorage.setItem('lms_last_version', currentVersion);
      } catch (e) {
          console.error("Failed to check version", e);
      }
  }

  function isNewer(v1, v2) {
      const parts1 = v1.split('.').map(Number);
      const parts2 = v2.split('.').map(Number);
      for (let i = 0; i < Math.max(parts1.length, parts2.length); i++) {
          const p1 = parts1[i] || 0;
          const p2 = parts2[i] || 0;
          if (p1 > p2) return true;
          if (p1 < p2) return false;
      }
      return false;
  }

  onMount(checkVersion);

  /**
   * Updates the global active view state.
   *
   * @param {string} view - The view identifier.
   */
  function handleNavigate(view) {
    activeView.set(view);
  }

</script>

<div class="flex items-center justify-between mb-6 sticky top-0 z-30 py-2 bg-[#121212]/90 backdrop-blur-md px-4 -mx-4">
  <div class="flex items-center gap-4 flex-grow">
    {#if hasDrawer}
      <button
        class="md:hidden flex items-center justify-center w-9 h-9 shrink-0 rounded-full bg-transparent border-none text-white hover:bg-[#282828] transition-colors cursor-pointer"
        aria-label={$t('nav.openMenu')}
        onclick={() => sidebarDrawerOpen.set(true)}
      >
        <Menu size={22} />
      </button>
    {/if}

    {#if $activeView === 'home'}
        <h1 class="text-xl md:text-3xl font-bold ml-2 whitespace-nowrap">{greeting}</h1>
    {/if}
    
    <SearchBar />
  </div>

  <div class="flex items-center gap-4">
    <ProfileButton onNavigate={handleNavigate} />
  </div>
</div>

{#if $activeModal?.type === 'release-notes'}
    <ReleaseNotesModal releases={$activeModal.data.releases} />
{/if}
