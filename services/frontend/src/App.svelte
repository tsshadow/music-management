<script>
  import { onMount } from 'svelte';
  import { fade, fly } from 'svelte/transition';
  import Sidebar from './lib/Sidebar.svelte';
  import Player from './lib/Player.svelte';
  import Dashboard from './lib/Dashboard.svelte';
  import LoginPage from './lib/LoginPage.svelte';
  import TopBar from './lib/TopBar.svelte';
  import TrackList from './lib/TrackList.svelte';
  import MobileNav from './lib/MobileNav.svelte';
  import SettingsSidebar from './lib/SettingsSidebar.svelte';
  import ManagementSidebar from './lib/management/ManagementSidebar.svelte';
  import SearchMoreModal from './lib/SearchMoreModal.svelte';
  import Toaster from './lib/Toaster.svelte';
  import { notify } from './lib/notifications.js';
  import { playlist, activeView, activeManagementTab, activeSettingsTab, currentPlaylist, currentTrack, isMobile, authParams, viewMode, activeModal, isAdmin, credentials, mumaSessionActive, pushedHistoryEntries, sidebarDrawerOpen, restUrl } from './lib/store.js';
  import { get } from 'svelte/store';
  import { pathToState, viewToPath } from './lib/router.js';
  import { platform } from './lib/platform/index.js';
  import { deepLinkAction, randomTracksUrl } from './lib/shellRoutes.js';
  import { t } from './lib/i18n/index.js';

  const hours = new Date().getHours();
  const greetingKey = hours < 12 ? 'greeting.morning' : hours < 18 ? 'greeting.afternoon' : 'greeting.evening';
  // Derived rather than assigned once, so the greeting follows a language change.
  const greeting = $derived($t(greetingKey));

  let showQueue = $state(false);

  $effect(() => {
    if ($viewMode === 'sets') {
        document.documentElement.classList.add('mode-sets');
        if ($activeView === 'songs') activeView.set('sets');
    } else {
        document.documentElement.classList.remove('mode-sets');
        if ($activeView === 'sets') activeView.set('songs');
    }
  });

  // Non-admins have no management UI at all: bounce them back home if they
  // land on '/management' (e.g. a stale persisted view, or a direct URL).
  // $isAdmin === false only once the admin check has actually resolved, so
  // this doesn't flicker admins away while their status is still loading.
  $effect(() => {
    if ($activeView === 'management' && $isAdmin === false) {
        activeView.set('home');
    }
  });

  // The drawer belongs to the settings/management shell. Leaving that shell
  // (including from the switch inside the drawer's own header) has to take the
  // overlay with it, otherwise it hangs over the player.
  const hasDrawer = $derived($activeView === 'settings' || $activeView === 'management');
  $effect(() => {
    if (!hasDrawer) sidebarDrawerOpen.set(false);
  });

  function closeDrawer() {
    sidebarDrawerOpen.set(false);
  }

  function handleDrawerKeydown(e) {
    if (e.key === 'Escape') closeDrawer();
  }

  let queueWidth = $state(350);
  let isResizing = $state(false);

  function startResizing(_e) {
    isResizing = true;
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', stopResizing);
  }

  function handleMouseMove(e) {
    if (!isResizing) return;
    const newWidth = window.innerWidth - e.clientX;
    if (newWidth > 200 && newWidth < 800) {
      queueWidth = newWidth;
    }
  }

  function stopResizing() {
    isResizing = false;
    document.removeEventListener('mousemove', handleMouseMove);
    document.removeEventListener('mouseup', stopResizing);
  }

  let isMounted = $state(false);

  /**
   * Moves the app onto the view a URL describes.
   *
   * Fields the path doesn't mention are left alone on purpose: '/settings'
   * without a tab keeps whichever tab the store remembers, rather than
   * bouncing the user back to the first one on every visit.
   *
   * @param {Object} state - The view state parsed out of the path.
   */
  function applyState(state) {
    if (state.view === 'sets') {
        viewMode.set('sets');
    } else if (state.view === 'songs') {
        viewMode.set('songs');
    }

    if (state.playlistId) currentPlaylist.set({ id: state.playlistId });
    if (state.settingsTab) activeSettingsTab.set(state.settingsTab);
    if (state.managementTab) activeManagementTab.set(state.managementTab);

    activeView.set(state.view);
  }

  onMount(() => {
    isMounted = true;
    const updateMobile = () => {
      isMobile.set(window.innerWidth < 1024 || window.matchMedia("(pointer: coarse)").matches);
    };
    updateMobile();
    window.addEventListener('resize', updateMobile);

    if (!get(credentials).username && !get(mumaSessionActive)) {
        activeView.set('login');
    } else {
        applyState(pathToState(window.location.pathname));
    }

    window.addEventListener('popstate', () => {
        applyState(pathToState(window.location.pathname));
        pushedHistoryEntries.update((n) => Math.max(0, n - 1));
    });

    // The two things only a shell sends. Both are no-ops in a browser, so there
    // is no platform check around them -- that is what the interface is for.
    const unsubscribes = [
      platform.system.onBack(handleShellBack),
      platform.system.onDeepLink(handleDeepLink),
    ];
    return () => {
      for (const unsubscribe of unsubscribes) unsubscribe();
    };
  });

  /**
   * The platform back gesture, which is not browser history.
   *
   * Runs to completion before anything is awaited: the shell gives the web UI a
   * 350 ms window to say it used the press and finishes the activity if it does
   * not, so an await here would be a coin flip between closing a sheet and
   * closing the app.
   *
   * Order matters and is the order things are stacked on screen: a modal is
   * over the drawer, the drawer over the queue panel, and only then is there
   * nothing left but a page to go back to. Returning false is what lets the
   * press leave the app, which is what back at the top of an app should do.
   *
   * @returns {boolean} Whether the press was used.
   */
  function handleShellBack() {
    if (get(activeModal)) {
      activeModal.set(null);
      return true;
    }
    if (get(sidebarDrawerOpen)) {
      sidebarDrawerOpen.set(false);
      return true;
    }
    if (showQueue) {
      showQueue = false;
      return true;
    }
    if (get(pushedHistoryEntries) > 0) {
      window.history.back();
      return true;
    }
    return false;
  }

  /**
   * A route from outside the app: the quick-settings tile, the car-mode
   * notification, a launcher shortcut, a "play from search" intent.
   *
   * @param {string} route
   */
  async function handleDeepLink(route) {
    const action = deepLinkAction(route);
    platform.diagnostics.log('deeplink', { route, unbuilt: action.unbuilt ?? null });
    if (action.kind === 'queue') {
      showQueue = true;
      return;
    }
    if (action.kind === 'random') {
      await playRandom();
      return;
    }
    activeView.set(action.view);
  }

  /**
   * Fills the queue with random tracks in the mode the listener is in and
   * starts it. This is what the car-mode "play something" intent has always
   * meant, and the player component takes it from the stores as usual.
   */
  async function playRandom() {
    try {
      const response = await fetch(restUrl(randomTracksUrl({ mode: get(viewMode), auth: get(authParams) })));
      const body = await response.json();
      const node = body['subsonic-response']?.tracks?.track ?? [];
      const tracks = Array.isArray(node) ? node : [node];
      if (!tracks.length) {
        notify.error($t('notify.noRandomTracks'));
        return;
      }
      playlist.set(tracks);
      currentTrack.set(tracks[0]);
    } catch (e) {
      console.error('Could not start random playback', e);
      notify.error($t('notify.noRandomTracks'), { detail: e.message });
    }
  }

  $effect(() => {
    if (isMounted) {
        const path = viewToPath({
            view: $activeView,
            loggedIn: Boolean($credentials.username) || $mumaSessionActive,
            playlistId: $currentPlaylist?.id,
            settingsTab: $activeSettingsTab,
            managementTab: $activeManagementTab
        });
        if (path && path !== window.location.pathname) {
            window.history.pushState({}, '', path);
            pushedHistoryEntries.update((n) => n + 1);
        }
    }
  });

  function handleNavigate(view) {
    // The action trail a crash report reads back. Navigation and play/pause are
    // the two that make a report tell a story; anything more would be noise in
    // a fifty-line buffer.
    platform.diagnostics.log('navigate', { view });
    activeView.set(view);
  }

  async function saveQueueAsPlaylist() {
      const tracks = get(playlist);
      if (tracks.length === 0) return;
      const name = prompt("Geef een naam voor de nieuwe afspeellijst:");
      if (!name) return;
      try {
          const songIds = tracks.map(t => t.id).join('&songId=');
          const auth = get(authParams);
          const resp = await fetch(restUrl(`/rest/createPlaylist?name=${encodeURIComponent(name)}&songId=${songIds}&${auth}`));
          if (!resp.ok) throw new Error(resp.statusText || `HTTP ${resp.status}`);
          notify.success($t('notify.queueSaved'));
      } catch (e) {
          console.error(e);
          notify.error($t('notify.queueSaveFailed'), { detail: e.message });
      }
  }

  function clearQueue() {
      playlist.set([]);
  }

  function shuffleQueue() {
      playlist.update(p => {
          const newP = [...p];
          for (let i = newP.length - 1; i > 0; i--) {
              const j = Math.floor(Math.random() * (i + 1));
              [newP[i], newP[j]] = [newP[j], newP[i]];
          }
          return newP;
      });
  }
</script>

<svelte:window onkeydown={handleDrawerKeydown} />

{#if !$credentials.username && !$mumaSessionActive}
  <LoginPage />
{:else}
<main class="grid grid-cols-1 md:grid-cols-[240px_1fr_auto] grid-rows-[1fr_auto_auto] md:grid-rows-[1fr_90px] h-dvh w-screen overflow-hidden bg-black text-white">
  <div class="bg-black row-start-1 row-end-2 col-start-1 col-end-2 overflow-y-auto min-h-0 hidden md:block">
    {#if $activeView === 'settings'}
      <SettingsSidebar onnavigate={handleNavigate} />
    {:else if $activeView === 'management'}
      <ManagementSidebar onnavigate={handleNavigate} />
    {:else}
      <Sidebar activeView={$activeView} onnavigate={handleNavigate} />
    {/if}
  </div>

  <div class="bg-linear-to-b from-[#121212] to-[#121212] row-start-1 row-end-2 col-start-1 md:col-start-2 col-end-2 md:col-end-3 overflow-y-auto p-4 md:p-8 relative min-h-0 min-w-0">
    <TopBar greeting={greeting} />
    <div class="content-area">
      <!-- Bound, not passed: Dashboard writes the view itself when a card, a track or
           an edit page navigates, and an unbound copy left those moves out of the store
           and so out of the URL -- which is what put the back button a page behind. -->
      <Dashboard bind:activeView={$activeView} onnavigate={handleNavigate} />
    </div>
  </div>

  {#if showQueue && !$isMobile}
    <div class="relative row-start-1 row-end-2 col-start-3 col-end-4 flex min-h-0 hidden md:flex">
      <button
        aria-label={$t('queue.resize')}
        class="w-1 bg-transparent border-none cursor-col-resize hover:bg-brand transition-colors z-10 p-0"
        onmousedown={startResizing}
      ></button>

      <div
        class="bg-[#121212] border-l border-[#282828] overflow-y-auto p-5 min-h-0"
        style="width: {queueWidth}px"
      >
          <header class="flex justify-between items-center mb-5">
              <h2 class="text-lg font-bold m-0">{$t('queue.title')}</h2>
              <div class="flex items-center gap-3">
                  <button class="flex items-center justify-center w-8 h-8 rounded-full bg-transparent text-[#b3b3b3] hover:bg-[#282828] hover:text-white transition-all cursor-pointer" onclick={saveQueueAsPlaylist} title={$t('queue.saveAsPlaylist')}>
                      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                          <path d="M19 12v7H5v-7H3v7c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2v-7h-2zm-6 .67l2.59-2.58L17 11.5l-5 5-5-5 1.41-1.41L11 12.67V3h2v9.67z"></path>
                      </svg>
                  </button>
                  <button class="flex items-center justify-center w-8 h-8 rounded-full bg-transparent text-[#b3b3b3] hover:bg-[#282828] hover:text-white transition-all cursor-pointer" onclick={shuffleQueue} title={$t('queue.shuffle')}>
                      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                          <path d="M4.5 6.307a.75.75 0 1 1 0-1.5 5.862 5.862 0 0 1 4.671 2.382l.66.883 5.03 6.717a4.362 4.362 0 0 0 3.471 1.769h1.918a.75.75 0 1 1 0 1.5h-1.918a5.862 5.862 0 0 1-4.671-2.381l-.66-.883-5.03-6.717a4.362 4.362 0 0 0-3.471-1.77H4.5zM14.862 8.567l.66-.883A5.862 5.862 0 0 1 20.193 5.3h1.057a.75.75 0 1 1 0 1.5h-1.057a4.362 4.362 0 0 0-3.471 1.768l-.66.883-.16-.214-.132-.176-.908-1.213-.01.014zM4.5 19.193a.75.75 0 1 0 0-1.5h1.057a4.362 4.362 0 0 0 3.471-1.768l.66-.883.908 1.213.14.186.124.166.01-.013.66.883A5.862 5.862 0 0 1 16.208 20.193H4.5z"></path>
                      </svg>
                  </button>
                  <button class="flex items-center justify-center w-8 h-8 rounded-full bg-transparent text-[#b3b3b3] hover:bg-[#282828] hover:text-white transition-all cursor-pointer" onclick={clearQueue} title={$t('queue.clear')}>
                      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                          <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"></path>
                      </svg>
                  </button>
                  <button class="bg-none border-none text-[#b3b3b3] text-2xl cursor-pointer px-2" onclick={() => showQueue = false}>&times;</button>
              </div>
          </header>
          <TrackList tracks={$playlist} isQueue={true} onnavigate={handleNavigate} />
      </div>
    </div>
  {/if}

  <div class="bg-[#181818] col-start-1 col-end-2 md:col-end-4 row-start-2 row-end-3 border-t border-[#282828] z-20 min-h-[64px] md:min-h-0">
    <Player
      ontoggleQueue={() => showQueue = !showQueue}
      onnavigate={handleNavigate}
    />
  </div>

  <div class="row-start-3 row-end-4 md:hidden z-20">
    <MobileNav activeView={$activeView} onnavigate={handleNavigate} />
  </div>

  <!-- Below `md` the sidebar column is hidden and the bottom bar has no entry
       for the settings/management tabs, so the same sidebar is offered as a
       drawer instead. -->
  {#if hasDrawer && $sidebarDrawerOpen}
    <div class="md:hidden fixed inset-0 z-40 flex" role="dialog" aria-modal="true" aria-label={$t('nav.menu')}>
      <button
        class="absolute inset-0 w-full h-full bg-black/70 backdrop-blur-sm border-none cursor-default"
        aria-label={$t('nav.closeMenu')}
        onclick={closeDrawer}
        transition:fade={{ duration: 150 }}
      ></button>
      <div
        class="relative w-[280px] max-w-[85vw] h-full bg-black border-r border-[#282828] overflow-y-auto shadow-2xl"
        transition:fly={{ x: -280, duration: 200 }}
      >
        {#if $activeView === 'settings'}
          <SettingsSidebar onnavigate={handleNavigate} onselect={closeDrawer} />
        {:else}
          <ManagementSidebar onnavigate={handleNavigate} onselect={closeDrawer} />
        {/if}
      </div>
    </div>
  {/if}
</main>
{/if}

{#if $activeModal}
  {#if $activeModal.type === 'search-results'}
    <SearchMoreModal query={$activeModal.data.query} category={$activeModal.data.category} />
  {/if}
{/if}

<!-- Outside the logged-in branch on purpose: a failure on the login screen
     has the same right to be seen as one inside the app. Renders nothing
     while there is nothing to report. -->
<Toaster />

<style>
  :global(body) {
    margin: 0;
    padding: 0;
    overflow: hidden;
  }
</style>
