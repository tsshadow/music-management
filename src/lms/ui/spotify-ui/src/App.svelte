<script>
  import { onMount } from 'svelte';
  import Sidebar from './lib/Sidebar.svelte';
  import Player from './lib/Player.svelte';
  import Dashboard from './lib/Dashboard.svelte';
  import AuthOverlay from './lib/AuthOverlay.svelte';
  import TopBar from './lib/TopBar.svelte';
  import TrackList from './lib/TrackList.svelte';
  import MobileNav from './lib/MobileNav.svelte';
  import SettingsSidebar from './lib/SettingsSidebar.svelte';
  import { playlist, activeView, currentPlaylist, isMobile } from './lib/store.js';

  let greeting = "";
  const hours = new Date().getHours();
  if (hours < 12) greeting = "Goedemorgen";
  else if (hours < 18) greeting = "Goedemiddag";
  else greeting = "Goedenavond";

  let showQueue = false;
  let queueWidth = 350;
  let isResizing = false;

  /**
   * Starts the resizing process for the queue sidebar.
   * 
   * @param {MouseEvent} _e - The mouse event.
   */
  function startResizing(_e) {
    isResizing = true;
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', stopResizing);
  }

  /**
   * Handles the mouse move event to update the queue sidebar width.
   * 
   * @param {MouseEvent} e - The mouse event.
   */
  function handleMouseMove(e) {
    if (!isResizing) return;
    const newWidth = window.innerWidth - e.clientX;
    if (newWidth > 200 && newWidth < 800) {
      queueWidth = newWidth;
    }
  }

  /**
   * Stops the resizing process and cleans up event listeners.
   */
  function stopResizing() {
    isResizing = false;
    document.removeEventListener('mousemove', handleMouseMove);
    document.removeEventListener('mouseup', stopResizing);
  }

  let isMounted = false;

  const base = '/spotify';

  /**
   * Maps a view name and optional playlist object to a URL path.
   * 
   * @param {string} view - The name of the active view.
   * @param {Object} [_playlistObj] - Optional playlist metadata.
   * @returns {string|null} The URL path.
   */
  function viewToPath(view, _playlistObj) {
    if (view === 'home') return base + '/';
    if (view === 'songs') return base + '/songs';
    if (view === 'sets') return base + '/sets';
    if (view === 'albums') return base + '/albums';
    if (view === 'artists') return base + '/artists';
    if (view === 'playlists') return base + '/playlists';
    if (view.startsWith('genre:')) return base + '/genre/' + view.split(':')[1];
    if (view.startsWith('artist:')) return base + '/artist/' + view.split(':')[1];
    if (view.startsWith('album:')) return base + '/album/' + view.split(':')[1];
    if (view === 'settings') return base + '/settings';
    return null;
  }

  /**
   * Maps a URL path back to a view name or view object.
   * 
   * @param {string} path - The URL path.
   * @returns {string|Object} The view identifier.
   */
  function pathToView(path) {
    if (path === base || path === base + '/') return 'home';
    if (path === base + '/songs') return 'songs';
    if (path === base + '/sets') return 'sets';
    if (path === base + '/albums') return 'albums';
    if (path === base + '/artists') return 'artists';
    if (path === base + '/playlists') return 'playlists';
    if (path.startsWith(base + '/genre/')) return 'genre:' + decodeURIComponent(path.slice((base + '/genre/').length));
    if (path.startsWith(base + '/artist/')) return 'artist:' + path.slice((base + '/artist/').length);
    if (path.startsWith(base + '/album/')) return 'album:' + path.slice((base + '/album/').length);
    if (path.startsWith(base + '/playlist/')) {
        const id = path.slice((base + '/playlist/').length);
        return { view: 'playlist-detail', id };
    }
    if (path === base + '/settings') return 'settings';
    return 'home';
  }

  onMount(() => {
    isMounted = true;
    
    const updateMobile = () => {
      isMobile.set(window.innerWidth < 1024 || window.matchMedia("(pointer: coarse)").matches);
    };
    updateMobile();
    window.addEventListener('resize', updateMobile);

    const initialView = pathToView(window.location.pathname);
    if (typeof initialView === 'object') {
        currentPlaylist.set({ id: initialView.id });
        activeView.set(initialView.view);
    } else {
        activeView.set(initialView);
    }

    window.addEventListener('popstate', () => {
        const view = pathToView(window.location.pathname);
        if (typeof view === 'object') {
            currentPlaylist.set({ id: view.id });
            activeView.set(view.view);
        } else {
            activeView.set(view);
        }
    });
  });

  $: {
    if (isMounted) {
        const path = viewToPath($activeView, $currentPlaylist);
        if (path && path !== window.location.pathname) {
            window.history.pushState({}, '', path);
        }
    }
  }

  /**
   * Updates the active view state.
   * 
   * @param {string|Object} view - The new view identifier.
   */
  function handleNavigate(view) {
    activeView.set(view);
  }

  /**
   * Clears all tracks from the global playlist/queue.
   */
  function clearQueue() {
      playlist.set([]);
  }

  /**
   * Shuffles the global playlist/queue randomly.
   */
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

<main class="grid grid-cols-1 md:grid-cols-[240px_1fr_auto] grid-rows-[1fr_auto_auto] md:grid-rows-[1fr_90px] h-dvh w-screen overflow-hidden bg-black text-white">
  <AuthOverlay />
  
  <div class="bg-black row-start-1 row-end-2 col-start-1 col-end-2 overflow-y-auto min-h-0 hidden md:block">
    {#if $activeView === 'settings'}
      <SettingsSidebar />
    {:else}
      <Sidebar activeView={$activeView} onnavigate={handleNavigate} />
    {/if}
  </div>
  
  <div class="bg-linear-to-b from-[#121212] to-[#121212] row-start-1 row-end-2 col-start-1 md:col-start-2 col-end-2 md:col-end-3 overflow-y-auto p-4 md:p-8 relative min-h-0 min-w-0">
    <TopBar {greeting} />

    <div class="content-area">
      <Dashboard bind:activeView={$activeView} />
    </div>
  </div>

  {#if showQueue && !$isMobile}
    <div class="relative row-start-1 row-end-2 col-start-3 col-end-4 flex min-h-0 hidden md:flex">
      <!-- Resize Handle -->
      <button 
        aria-label="Wachtrij resizen"
        class="w-1 bg-transparent border-none cursor-col-resize hover:bg-spotify-green transition-colors z-10 p-0"
        on:mousedown={startResizing}
      ></button>
      
      <div 
        class="bg-[#121212] border-l border-[#282828] overflow-y-auto p-5 min-h-0"
        style="width: {queueWidth}px"
      >
          <header class="flex justify-between items-center mb-5">
              <h2 class="text-lg font-bold m-0">Wachtrij</h2>
              <div class="flex items-center gap-3">
                  <button class="flex items-center justify-center w-8 h-8 rounded-full bg-transparent text-[#b3b3b3] hover:bg-[#282828] hover:text-white transition-all cursor-pointer" on:click={shuffleQueue} title="Shuffle">
                      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                          <path d="M4.5 6.307a.75.75 0 1 1 0-1.5 5.862 5.862 0 0 1 4.671 2.382l.66.883 5.03 6.717a4.362 4.362 0 0 0 3.471 1.769h1.918a.75.75 0 1 1 0 1.5h-1.918a5.862 5.862 0 0 1-4.671-2.381l-.66-.883-5.03-6.717a4.362 4.362 0 0 0-3.471-1.77H4.5zM14.862 8.567l.66-.883A5.862 5.862 0 0 1 20.193 5.3h1.057a.75.75 0 1 1 0 1.5h-1.057a4.362 4.362 0 0 0-3.471 1.768l-.66.883-.16-.214-.132-.176-.908-1.213-.01.014zM4.5 19.193a.75.75 0 1 0 0-1.5h1.057a4.362 4.362 0 0 0 3.471-1.768l.66-.883.908 1.213.14.186.124.166.01-.013.66.883A5.862 5.862 0 0 1 16.208 20.193H4.5z"></path>
                      </svg>
                  </button>
                  <button class="flex items-center justify-center w-8 h-8 rounded-full bg-transparent text-[#b3b3b3] hover:bg-[#282828] hover:text-white transition-all cursor-pointer" on:click={clearQueue} title="Lijst leegmaken">
                      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                          <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"></path>
                      </svg>
                  </button>
                  <button class="bg-none border-none text-[#b3b3b3] text-2xl cursor-pointer px-2" on:click={() => showQueue = false}>&times;</button>
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
</main>

<style>
  :global(body) {
    margin: 0;
    padding: 0;
    overflow: hidden;
  }
</style>
