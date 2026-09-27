<script>
  import { onMount } from 'svelte';
  import { fade, fly } from 'svelte/transition';
  import Sidebar from './lib/Sidebar.svelte';
  import Player from './lib/Player.svelte';
  import Dashboard from './lib/Dashboard.svelte';
  import QueueLoadMore from './lib/QueueLoadMore.svelte';
  import LoginPage from './lib/LoginPage.svelte';
  import OfflineNotice from './lib/OfflineNotice.svelte';
  import TopBar from './lib/TopBar.svelte';
  import TrackList from './lib/TrackList.svelte';
  import MobileNav from './lib/MobileNav.svelte';
  import MobileSearchView from './lib/MobileSearchView.svelte';
  import SettingsSidebar from './lib/SettingsSidebar.svelte';
  import ManagementSidebar from './lib/management/ManagementSidebar.svelte';
  import SearchMoreModal from './lib/SearchMoreModal.svelte';
  import BottomSheet from './lib/BottomSheet.svelte';
  import Toaster from './lib/Toaster.svelte';
  import CarModeView from './lib/CarModeView.svelte';
  import SetupWizard from './lib/SetupWizard.svelte';
  import { notify } from './lib/notifications.js';
  import { playlist, activeView, activeManagementTab, activeSettingsTab, currentPlaylist, currentTrack, isMobile, authParams, viewMode, activeModal, isAdmin, credentials, mumaSessionActive, pushedHistoryEntries, sidebarDrawerOpen, searchResultsOpen, restUrl, nowPlayingOpen, openNowPlaying, closeNowPlaying, setupStepsSeen, accountSettingsSynced, mumaUserHydrated, subsonicAccess, ensureSubsonicToken, endRejectedSession } from './lib/store.js';
  import { get } from 'svelte/store';
  import { modeForView, pathToState, viewToPath } from './lib/router.js';
  import { platform } from './lib/platform/index.js';
  import { watchConnectivity } from './lib/subsonic.js';
  import { deepLinkAction, randomTracksUrl } from './lib/shellRoutes.js';
  import { createCarModeSession, CarModeIntent } from './lib/carMode.js';
  import { t } from './lib/i18n/index.js';
  import { logAction } from './lib/diagnosticsLog.js';
  import { checkForMobileUpdate } from './lib/mobileReleaseNotes.js';
  import { checkForAppUpdate } from './lib/appUpdate.js';
  import { allSteps, isUpdateRun, pendingSteps } from './lib/setup.js';
  import { recordPlace } from './lib/recentPlaces.js';
  import { startQueue, saveTracksAsPlaylist } from './lib/queue.js';

  const hours = new Date().getHours();
  const greetingKey = hours < 12 ? 'greeting.morning' : hours < 18 ? 'greeting.afternoon' : 'greeting.evening';
  // Derived rather than assigned once, so the greeting follows a language change.
  const greeting = $derived($t(greetingKey));

  let showQueue = $state(false);

  // The view to return to when the car screen closes. `carModeSession` is the ported
  // `car/CarModeSession.kt`: it decides whether `carConnected` firing again this trip should
  // reopen the screen, independently of whatever the native notification is doing with the
  // same signal (see `lib/carMode.js`).
  const carModeSession = createCarModeSession();
  let carReturnView = 'home';

  $effect(() => {
    if ($viewMode === 'sets') {
        document.documentElement.classList.add('mode-sets');
        if ($activeView === 'songs') activeView.set('sets');
    } else {
        document.documentElement.classList.remove('mode-sets');
        if ($activeView === 'sets') activeView.set('songs');
    }
  });

  // The setup tour. Opens on its own once the account's settings are known -- not
  // before, or an account that finished the tour on another device would be walked
  // through it again on every new one -- when a step is pending: every step on a first
  // run, the new ones after an update that added a step (see `lib/setup.js`). Once per
  // session at most: finishing or skipping records the steps, so a second offer would
  // only ever be a bug reopening the same screen. By hand (the manual's "run the tour
  // again") the same view walks every step, badged as nothing.
  let setupOffered = false;
  let setupReturnView = 'home';
  const setupPending = $derived(pendingSteps($setupStepsSeen, platform));
  const setupSteps = $derived(setupPending.length > 0 ? setupPending : allSteps(platform));
  const setupIsUpdate = $derived(setupPending.length > 0 && isUpdateRun($setupStepsSeen));
  $effect(() => {
    if (setupOffered || !isMounted) return;
    if (!$mumaUserHydrated || !$accountSettingsSynced) return;
    if (!$credentials.username && !$mumaSessionActive) return;
    if (['login', 'setup', 'car', 'voice'].includes($activeView)) return;
    if (setupPending.length === 0) return;
    setupOffered = true;
    setupReturnView = $activeView;
    activeView.set('setup');
  });

  /** The tour is over: back to where the listener was, or on to the manual it pointed at. */
  function handleSetupClose(destination) {
    if (destination === 'help') {
      activeSettingsTab.set('help');
      activeView.set('settings');
      return;
    }
    activeView.set(setupReturnView === 'setup' ? 'home' : setupReturnView);
  }

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

  // The search results panel is SearchBar's own state, mirrored into the store
  // so the shell's back handler can close it; leaving the Search tab any other
  // way (tapping Home, following a link) should not leave that mirror stuck on
  // true for a back press made somewhere else entirely.
  $effect(() => {
    if ($activeView !== 'search' && $activeView !== 'browse') searchResultsOpen.set(false);
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
    const mode = modeForView(state.view);
    if (mode) viewMode.set(mode);

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
        // Now Playing pushed its own entry on open (see `openNowPlaying`). A
        // real, external back press -- a browser back button with no shell in
        // front of it -- lands here first and is what actually has to close
        // the view; `closeNowPlaying` (the chevron, a swipe, the shell's own
        // back gesture) already flipped `nowPlayingOpen` before this fires, so
        // this branch is skipped then and the fall-through below only
        // consumes the entry.
        if (get(nowPlayingOpen)) {
          nowPlayingOpen.set(false);
          pushedHistoryEntries.update((n) => Math.max(0, n - 1));
          return;
        }
        applyState(pathToState(window.location.pathname));
        pushedHistoryEntries.update((n) => Math.max(0, n - 1));
    });

    // The three things only a shell sends. All are no-ops in a browser, so there
    // is no platform check around any of them -- that is what the interface is for.
    const unsubscribes = [
      platform.system.onBack(handleShellBack),
      platform.system.onDeepLink(handleDeepLink),
      platform.system.carConnected(handleCarPresence),
      // Also a no-op in a browser: `platform.storage.supported` is false there,
      // `offline` never becomes true, and no screen changes.
      watchConnectivity(platform),
    ];

    // A cold start already in the car: `carConnected` only reaches a listener that
    // subscribed before the shell fired it, so a boot that missed the event asks once
    // instead. Read after subscribing, not before -- a connection that happens in
    // between is still caught by the listener above, and `onPresenceChanged` treats a
    // second report of the same state as nothing, so there is no double-navigate.
    platform.system.carState()
      .then((state) => handleCarPresence(state.connected))
      .catch(() => {});

    // No-op in a browser tab, same as the three subscriptions above: a plain
    // `isNative` check inside, so there is no platform branch here either.
    checkForMobileUpdate().catch(() => {});
    // Looks the other way: whether a newer APK exists. Once a day, quiet unless there is one.
    checkForAppUpdate().catch(() => {});

    return () => {
      for (const unsubscribe of unsubscribes) unsubscribe();
    };
  });

  /**
   * `platform.system.carConnected`, and the bootstrap read of `carState()`. Both feed the same
   * ported state machine, so a screen already open when the trip ends is exactly the thing that
   * closes it, and a screen the driver dismissed does not reopen on the next duplicate report.
   *
   * @param {boolean} connected
   */
  function handleCarPresence(connected) {
    const intent = carModeSession.onPresenceChanged(connected);
    if (intent === CarModeIntent.OFFER) enterCarMode();
    else if (intent === CarModeIntent.CLOSE && get(activeView) === 'car') {
      activeView.set(carReturnView);
    }
  }

  /** Remembers where to return to, then switches -- shared by the auto-open path and the
   *  overflow menu's own "Carmodus" entry (see `handleNavigate`). */
  function enterCarMode() {
    if (get(activeView) === 'car') return;
    carReturnView = get(activeView);
    activeView.set('car');
  }

  /** The car screen's own close button. Recorded as a dismissal so a duplicate `carConnected`
   *  report for the same trip does not reopen it; a real disconnect and reconnect still will. */
  function handleCarClose() {
    carModeSession.onDismissed();
    activeView.set(carReturnView);
  }

  /**
   * The platform back gesture, which is not browser history.
   *
   * Runs to completion before anything is awaited: the shell gives the web UI a
   * 350 ms window to say it used the press and finishes the activity if it does
   * not, so an await here would be a coin flip between closing a sheet and
   * closing the app.
   *
   * Order matters and is the order things are stacked on screen: a modal is
   * over the search results panel, which is over the drawer, which is over
   * the queue panel, and only then is there nothing left but a page to go
   * back to. Returning false is what lets the press leave the app, which is
   * what back at the top of an app should do.
   *
   * @returns {boolean} Whether the press was used.
   */
  function handleShellBack() {
    // Above everything else on screen (z-50; see CarModeView), so it is checked first.
    // Goes through the same close path as the screen's own button -- not
    // `pushedHistoryEntries` below -- so a dismissal by the hardware gesture is recorded
    // the same as a tap, and a duplicate `carConnected` report right after does not
    // reopen it.
    if (get(activeView) === 'car') {
      handleCarClose();
      return true;
    }
    // Now Playing's own queue button opens the same bottom sheet as the
    // mini player's, stacked on top of it -- so a press while both are open
    // has to close the sheet first (the `showQueue` branch further down) and
    // leave Now Playing for the next one, rather than close what looks like
    // nothing from on top of the sheet.
    if (get(nowPlayingOpen) && !showQueue) {
      closeNowPlaying();
      return true;
    }
    if (get(activeModal)) {
      activeModal.set(null);
      return true;
    }
    if (get(searchResultsOpen)) {
      searchResultsOpen.set(false);
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
    const action = deepLinkAction(route, { isMobile: get(isMobile) });
    logAction('deeplink', { route, unbuilt: action.unbuilt ?? null });
    if (action.kind === 'queue') {
      showQueue = true;
      return;
    }
    if (action.kind === 'now-playing') {
      openNowPlaying();
      return;
    }
    if (action.kind === 'random') {
      await playRandom();
      return;
    }
    // The car-mode notification's own tap: an explicit ask, not the auto-open gate
    // `carModeSession` guards, so it always opens the screen regardless of an earlier
    // dismissal this trip. Goes through `enterCarMode` rather than a bare
    // `activeView.set` so closing the screen still knows where to return to.
    if (action.view === 'car') {
      enterCarMode();
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
    logAction('navigate', { view });
    // The overflow menu's own "Carmodus" entry (ProfileButton, native only): an
    // explicit ask, so it opens the same way the notification tap does.
    if (view === 'car') {
      enterCarMode();
      return;
    }
    // 'playlist:<id>' is not itself a real `activeView`: a playlist opens as
    // 'playlist-detail' with the id living in the separate `currentPlaylist`
    // store instead (see router.js's own comment on the same quirk, and
    // `Dashboard.svelte`'s `openPlaylist`). The string exists only so recent
    // places has one navigable identifier per kind, like every other place;
    // this is the one spot every navigation passes through, so it is where
    // that string is translated back into the real mechanism.
    if (view.startsWith('playlist:')) {
      currentPlaylist.set({ id: view.slice('playlist:'.length) });
      activeView.set('playlist-detail');
      recordPlace(view);
      return;
    }
    // The mode first, then the view: the effect above reads both and corrects
    // whichever is behind, and it runs after this handler returns. Moving the
    // view alone to 'sets' while the mode still said 'songs' is what made the
    // "Sets" tab in the bottom bar land back on '/songs' every time.
    const mode = modeForView(view);
    if (mode) viewMode.set(mode);
    activeView.set(view);
    // Only views listed in `PLACE_PREFIXES` (recentPlaces.js) are actually kept;
    // recordPlace is a no-op for everything else (settings, 'home', ...).
    recordPlace(view);
  }

  async function saveQueueAsPlaylist() {
      const tracks = get(playlist);
      if (tracks.length === 0) return;
      const name = prompt($t('queue.playlistNamePrompt'));
      if (!name) return;
      try {
          await saveTracksAsPlaylist(name, tracks, get(authParams));
          notify.success($t('notify.queueSaved'));
      } catch (e) {
          console.error(e);
          notify.error($t('notify.queueSaveFailed'), { detail: e.message });
      }
  }

  function clearQueue() {
      // Clearing the queue also clears where it came from: an emptied queue
      // has no "playing from" to speak of.
      startQueue([], { view: null });
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
<!-- From `md` up (a tablet, a desktop) nothing else pads the system bars: the phone's TopBar
     and MobileNav carry their own insets, but a tablet shows the sidebar layout, and there the
     status bar sat over the MuMa logo and the navigation bar over the player controls. The top
     inset pads the whole grid; the bottom one grows the player row and pads its content. -->
<main class="grid grid-cols-1 md:grid-cols-[240px_1fr_auto] grid-rows-[1fr_auto_auto] md:grid-rows-[1fr_calc(90px+env(safe-area-inset-bottom,0px))] md:pt-[env(safe-area-inset-top,0px)] h-dvh w-screen overflow-hidden bg-black text-white">
  <div class="bg-black row-start-1 row-end-2 col-start-1 col-end-2 overflow-y-auto min-h-0 hidden md:block">
    {#if $activeView === 'settings'}
      <SettingsSidebar onnavigate={handleNavigate} />
    {:else if $activeView === 'management'}
      <ManagementSidebar onnavigate={handleNavigate} />
    {:else}
      <Sidebar activeView={$activeView} onnavigate={handleNavigate} />
    {/if}
  </div>

  <div class="bg-linear-to-b from-muma-spotify-dark to-muma-spotify-dark row-start-1 row-end-2 col-start-1 md:col-start-2 col-end-2 md:col-end-3 overflow-y-auto p-3 md:p-8 relative min-h-0 min-w-0">
    <TopBar greeting={greeting} />
    <div class="content-area">
      <!-- The desktop sidebar already offers the mode switch; on the phone it now lives in
           TopBar's own top bar, next to search and the profile button, instead of a row here. -->

      {#if $activeView === 'search' || $activeView === 'browse'}
        <div class="md:hidden">
          <MobileSearchView onnavigate={handleNavigate} />
        </div>
      {/if}

      <!-- Bound, not passed: Dashboard writes the view itself when a card, a track or
           an edit page navigates, and an unbound copy left those moves out of the store
           and so out of the URL -- which is what put the back button a page behind.
           Dashboard has no branch for 'search' (it is entirely phone content, above),
           so on that view this renders nothing and never fights MobileSearchView. -->
      <!-- Signed in without a Subsonic token nothing is requested at all (issue #72): say why,
           instead of a library that silently stays empty. -->
      {#if $subsonicAccess === 'offline'}
        <div class="mb-6"><OfflineNotice kind="server" onretry={() => ensureSubsonicToken()} /></div>
      {:else if $subsonicAccess === 'rejected'}
        <div class="mb-6"><OfflineNotice kind="signIn" onsignin={() => endRejectedSession()} /></div>
      {/if}
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
        class="bg-muma-spotify-dark border-l border-muma-spotify-light overflow-y-auto p-5 min-h-0"
        style="width: {queueWidth}px"
      >
          <header class="flex justify-between items-center mb-5">
              <h2 class="text-lg font-bold m-0">{$t('queue.title')}</h2>
              <div class="flex items-center gap-3">
                  <button class="flex items-center justify-center w-8 h-8 rounded-full bg-transparent text-muma-spotify-text hover:bg-muma-spotify-light hover:text-white transition-all cursor-pointer" onclick={saveQueueAsPlaylist} title={$t('queue.saveAsPlaylist')}>
                      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                          <path d="M19 12v7H5v-7H3v7c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2v-7h-2zm-6 .67l2.59-2.58L17 11.5l-5 5-5-5 1.41-1.41L11 12.67V3h2v9.67z"></path>
                      </svg>
                  </button>
                  <button class="flex items-center justify-center w-8 h-8 rounded-full bg-transparent text-muma-spotify-text hover:bg-muma-spotify-light hover:text-white transition-all cursor-pointer" onclick={shuffleQueue} title={$t('queue.shuffle')}>
                      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                          <path d="M4.5 6.307a.75.75 0 1 1 0-1.5 5.862 5.862 0 0 1 4.671 2.382l.66.883 5.03 6.717a4.362 4.362 0 0 0 3.471 1.769h1.918a.75.75 0 1 1 0 1.5h-1.918a5.862 5.862 0 0 1-4.671-2.381l-.66-.883-5.03-6.717a4.362 4.362 0 0 0-3.471-1.77H4.5zM14.862 8.567l.66-.883A5.862 5.862 0 0 1 20.193 5.3h1.057a.75.75 0 1 1 0 1.5h-1.057a4.362 4.362 0 0 0-3.471 1.768l-.66.883-.16-.214-.132-.176-.908-1.213-.01.014zM4.5 19.193a.75.75 0 1 0 0-1.5h1.057a4.362 4.362 0 0 0 3.471-1.768l.66-.883.908 1.213.14.186.124.166.01-.013.66.883A5.862 5.862 0 0 1 16.208 20.193H4.5z"></path>
                      </svg>
                  </button>
                  <button class="flex items-center justify-center w-8 h-8 rounded-full bg-transparent text-muma-spotify-text hover:bg-muma-spotify-light hover:text-white transition-all cursor-pointer" onclick={clearQueue} title={$t('queue.clear')}>
                      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                          <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"></path>
                      </svg>
                  </button>
                  <button class="bg-none border-none text-muma-spotify-text text-2xl cursor-pointer px-2" onclick={() => showQueue = false}>&times;</button>
              </div>
          </header>
          <TrackList tracks={$playlist} isQueue={true} onnavigate={handleNavigate} />
          <QueueLoadMore />
      </div>
    </div>
  {/if}

  <!-- z-40, not z-20: a grid item with a z-index is a stacking context, so the phone's
       full-screen Now Playing (`fixed inset-0 z-40` inside Player) can never rise above
       this number. At z-20 the content column's sticky TopBar (z-30) and the bottom nav
       (z-20, later in the DOM) both painted over it. The drawer below is z-40 too and
       later in the DOM, so it still wins; the z-[100] sheets and modals are untouched. -->
  <div class="bg-muma-spotify-panel col-start-1 col-end-2 md:col-end-4 row-start-2 row-end-3 border-t border-muma-spotify-light z-40 min-h-[64px] md:min-h-0 md:pb-[env(safe-area-inset-bottom,0px)]">
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
        class="relative w-[280px] max-w-[85vw] h-full bg-black border-r border-muma-spotify-light overflow-y-auto shadow-2xl pt-[env(safe-area-inset-top,0px)] pb-[env(safe-area-inset-bottom,0px)]"
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

  <!-- z-50: above Player's internal z-40 Now Playing and the z-40 drawer above, the
       highest anything in the app goes. MobileNav and the mini player stay mounted
       underneath rather than being torn down, so playback is untouched -- the point of
       this screen is that music keeps going while it is up. -->
  {#if $activeView === 'car'}
    <CarModeView onclose={handleCarClose} onmicrophone={() => handleNavigate('voice')} />
  {/if}

  <!-- Same layer as the car screen: a full-screen sheet over the app, player still mounted
       underneath. -->
  {#if $activeView === 'setup'}
    <SetupWizard steps={setupSteps} update={setupIsUpdate} {platform} onclose={handleSetupClose} />
  {/if}
</main>
{/if}

{#if showQueue && $isMobile}
  <!-- The phone has no room for the resizable desktop panel above, so the same
       queue -- same actions, same list -- opens as a bottom sheet instead.
       Reachable from the mini player's queue button and from Now Playing's. -->
  <BottomSheet title={$t('queue.title')} onclose={() => showQueue = false}>
    <div class="flex items-center gap-2 px-4 pb-3">
      <button class="flex items-center justify-center w-9 h-9 rounded-full bg-transparent text-muma-spotify-text hover:bg-white/10 hover:text-white transition-all cursor-pointer" onclick={saveQueueAsPlaylist} aria-label={$t('queue.saveAsPlaylist')}>
        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
          <path d="M19 12v7H5v-7H3v7c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2v-7h-2zm-6 .67l2.59-2.58L17 11.5l-5 5-5-5 1.41-1.41L11 12.67V3h2v9.67z"></path>
        </svg>
      </button>
      <button class="flex items-center justify-center w-9 h-9 rounded-full bg-transparent text-muma-spotify-text hover:bg-white/10 hover:text-white transition-all cursor-pointer" onclick={shuffleQueue} aria-label={$t('queue.shuffle')}>
        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
          <path d="M4.5 6.307a.75.75 0 1 1 0-1.5 5.862 5.862 0 0 1 4.671 2.382l.66.883 5.03 6.717a4.362 4.362 0 0 0 3.471 1.769h1.918a.75.75 0 1 1 0 1.5h-1.918a5.862 5.862 0 0 1-4.671-2.381l-.66-.883-5.03-6.717a4.362 4.362 0 0 0-3.471-1.77H4.5zM14.862 8.567l.66-.883A5.862 5.862 0 0 1 20.193 5.3h1.057a.75.75 0 1 1 0 1.5h-1.057a4.362 4.362 0 0 0-3.471 1.768l-.66.883-.16-.214-.132-.176-.908-1.213-.01.014zM4.5 19.193a.75.75 0 1 0 0-1.5h1.057a4.362 4.362 0 0 0 3.471-1.768l.66-.883.908 1.213.14.186.124.166.01-.013.66.883A5.862 5.862 0 0 1 16.208 20.193H4.5z"></path>
        </svg>
      </button>
      <button class="flex items-center justify-center w-9 h-9 rounded-full bg-transparent text-muma-spotify-text hover:bg-white/10 hover:text-white transition-all cursor-pointer" onclick={clearQueue} aria-label={$t('queue.clear')}>
        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
          <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"></path>
        </svg>
      </button>
    </div>
    <TrackList tracks={$playlist} isQueue={true} onnavigate={handleNavigate} />
    <QueueLoadMore />
  </BottomSheet>
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
