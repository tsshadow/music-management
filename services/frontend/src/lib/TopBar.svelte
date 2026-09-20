<script>
  import { onMount } from 'svelte';
  import ProfileButton from './ProfileButton.svelte';
  import SearchBar from './SearchBar.svelte';
  import ModeChips from './ModeChips.svelte';
  import ReleaseNotesModal from './ReleaseNotesModal.svelte';
  import { activeView, authParams, activeModal, sidebarDrawerOpen, searchResultsOpen, restUrl, isMobile } from './store.js';
  import { phoneTabForView } from './router.js';
  import { t } from './i18n/index.js';
  import { Menu, SlidersHorizontal } from '@lucide/svelte';
  import { get } from 'svelte/store';

  const { greeting = "" } = $props();

  // The bottom bar covers the player views, but it has no entry for the
  // settings and management tabs -- those only live in the sidebar, which is
  // hidden below `md`. So on those two views the top bar carries the opener.
  const hasDrawer = $derived($activeView === 'settings' || $activeView === 'management');

  // The phone's top bar carries the Songs/Sets mode control on the same tabs that used to
  // show it as its own row above the content -- Home, Bladeren and Favorieten -- using the
  // same helper MobileNav uses to keep a detail page's owning tab active.
  const phoneTab = $derived(phoneTabForView($activeView));

  async function checkVersion() {
      try {
          const auth = get(authParams);
          if (!auth) return;

          const response = await fetch(restUrl(`/rest/ping?${auth}`));
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

{#if $isMobile}
  <!-- Phone: one line -- search, then the Songs/Sets mode control, then the profile
       button. The mode control replaces the row `App.svelte` used to render above the
       content; it stays gated by `phoneTab` the same way that row was, so detail pages
       (an album, an artist) that have no tab of their own keep it hidden. Gated by
       `$isMobile` rather than the wider `md:hidden` alone -- see the same choice on
       `HomeShelf.svelte` -- with `md:hidden` kept alongside it as the CSS backstop the
       app's other phone/desktop forks (the queue panel below) also carry.

       This bar is also what covers the status bar: the app runs edge-to-edge in the WebView
       (`viewport-fit=cover` in index.html), so the top inset is padding here rather than a
       system strip the OS paints -- the bar is sticky, and its translucent ground is what
       scrolled content shows through under the clock, the way Spotify's does. `-mt-3` cancels
       the column's own top padding so nothing sits above the bar on first paint. -->
  <div class="md:hidden flex items-center gap-2 h-[calc(3rem+env(safe-area-inset-top,0px))] pt-[env(safe-area-inset-top,0px)] px-3 -mx-3 -mt-3 sticky top-0 z-30 mb-3 bg-[#121212]/90 backdrop-blur-md">
    {#if hasDrawer}
      <button
        class="flex items-center justify-center w-9 h-9 shrink-0 rounded-full bg-transparent border-none text-white hover:bg-[#282828] transition-colors cursor-pointer"
        aria-label={$t('nav.openMenu')}
        onclick={() => sidebarDrawerOpen.set(true)}
      >
        <Menu size={22} />
      </button>
    {/if}

    <SearchBar bind:showResults={$searchResultsOpen} />

    {#if phoneTab === 'browse'}
      <!-- The advanced-search entry used to be its own card at the top of Bladeren; a filter
           icon beside the search field puts it one tap away without spending a whole row on it. -->
      <button
        type="button"
        class="flex items-center justify-center w-9 h-9 shrink-0 rounded-full bg-transparent border-none text-white hover:bg-[#282828] transition-colors cursor-pointer"
        aria-label={$t('presetBuilder.open')}
        onclick={() => handleNavigate('new-preset')}
      >
        <SlidersHorizontal size={20} />
      </button>
    {/if}

    {#if phoneTab}
      <ModeChips />
    {/if}

    <ProfileButton onNavigate={handleNavigate} />
  </div>
{:else}
  <div class="hidden md:flex items-center justify-between mb-6 sticky top-0 z-30 py-2 bg-[#121212]/90 backdrop-blur-md px-4 -mx-4">
    <div class="flex items-center gap-4 flex-grow">
      {#if $activeView === 'home'}
          <!-- The phone Home already opens with its own quick-access grid; a "Goedemorgen"
               line above it only ate space the tiles could use, so the greeting stays
               desktop-only (this branch already is). -->
          <h1 class="text-xl md:text-3xl font-bold ml-2 whitespace-nowrap">{greeting}</h1>
      {/if}

      <SearchBar bind:showResults={$searchResultsOpen} />
    </div>

    <div class="flex items-center gap-4">
      <ProfileButton onNavigate={handleNavigate} />
    </div>
  </div>
{/if}

{#if $activeModal?.type === 'release-notes'}
    <ReleaseNotesModal releases={$activeModal.data.releases} />
{/if}
