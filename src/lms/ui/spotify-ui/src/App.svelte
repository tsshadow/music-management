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
  import SearchMoreModal from './lib/SearchMoreModal.svelte';
  import { playlist, activeView, currentPlaylist, isMobile, authParams, viewMode, activeModal } from './lib/store.js';
  import { get } from 'svelte/store';

  let greeting = $state("");
  const hours = new Date().getHours();
  if (hours < 12) greeting = "Goedemorgen";
  else if (hours < 18) greeting = "Goedemiddag";
  else greeting = "Goedenavond";

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
  const base = '/mumafi';

  function viewToPath(view, _playlistObj) {
    if (view === 'home') return base + '/';
    if (view === 'songs') return base + '/songs';
    if (view === 'sets') return base + '/sets';
    if (view === 'albums') return base + '/albums';
    if (view === 'genres') return base + '/genres';
    if (view === 'artists') return base + '/artists';
    if (view === 'playlists') return base + '/playlists';
    if (view.startsWith('genre:')) return base + '/genre/' + view.split(':')[1];
    if (view.startsWith('artist:')) return base + '/artist/' + view.split(':')[1];
    if (view.startsWith('album:')) return base + '/album/' + view.split(':')[1];
    if (view === 'settings') return base + '/settings';
    return null;
  }

  function pathToView(path) {
    if (path === base || path === base + '/') return 'home';
    if (path === base + '/songs') return 'songs';
    if (path === base + '/sets') return 'sets';
    if (path === base + '/albums') return 'albums';
    if (path === base + '/genres') return 'genres';
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
    if (initialView === 'sets') {
        viewMode.set('sets');
    } else if (initialView === 'songs') {
        viewMode.set('songs');
    }

    if (typeof initialView === 'object') {
        currentPlaylist.set({ id: initialView.id });
        activeView.set(initialView.view);
    } else {
        activeView.set(initialView);
    }

    window.addEventListener('popstate', () => {
        const view = pathToView(window.location.pathname);
        if (view === 'sets') {
            viewMode.set('sets');
        } else if (view === 'songs') {
            viewMode.set('songs');
        }

        if (typeof view === 'object') {
            currentPlaylist.set({ id: view.id });
            activeView.set(view.view);
        } else {
            activeView.set(view);
        }
    });
  });

  $effect(() => {
    if (isMounted) {
        const path = viewToPath($activeView, $currentPlaylist);
        if (path && path !== window.location.pathname) {
            window.history.pushState({}, '', path);
        }
    }
  });

  function handleNavigate(view) {
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
          const resp = await fetch(`/rest/createPlaylist?name=${encodeURIComponent(name)}&songId=${songIds}&${auth}`);
          if (resp.ok) alert("Afspeellijst opgeslagen!");
          else throw new Error("Failed");
      } catch (e) {
          console.error(e);
          alert("Fout bij het opslaan.");
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
    <TopBar greeting={greeting} />
    <div class="content-area">
      <Dashboard activeView={$activeView} onnavigate={handleNavigate} />
    </div>
  </div>

  {#if showQueue && !$isMobile}
    <div class="relative row-start-1 row-end-2 col-start-3 col-end-4 flex min-h-0 hidden md:flex">
      <button
        aria-label="Wachtrij resizen"
        class="w-1 bg-transparent border-none cursor-col-resize hover:bg-brand transition-colors z-10 p-0"
        onmousedown={startResizing}
      ></button>

      <div
        class="bg-[#121212] border-l border-[#282828] overflow-y-auto p-5 min-h-0"
        style="width: {queueWidth}px"
      >
          <header class="flex justify-between items-center mb-5">
              <h2 class="text-lg font-bold m-0">Wachtrij</h2>
              <div class="flex items-center gap-3">
                  <button class="flex items-center justify-center w-8 h-8 rounded-full bg-transparent text-[#b3b3b3] hover:bg-[#282828] hover:text-white transition-all cursor-pointer" onclick={saveQueueAsPlaylist} title="Opslaan als afspeellijst">
                      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                          <path d="M19 12v7H5v-7H3v7c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2v-7h-2zm-6 .67l2.59-2.58L17 11.5l-5 5-5-5 1.41-1.41L11 12.67V3h2v9.67z"></path>
                      </svg>
                  </button>
                  <button class="flex items-center justify-center w-8 h-8 rounded-full bg-transparent text-[#b3b3b3] hover:bg-[#282828] hover:text-white transition-all cursor-pointer" onclick={shuffleQueue} title="Shuffle">
                      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                          <path d="M4.5 6.307a.75.75 0 1 1 0-1.5 5.862 5.862 0 0 1 4.671 2.382l.66.883 5.03 6.717a4.362 4.362 0 0 0 3.471 1.769h1.918a.75.75 0 1 1 0 1.5h-1.918a5.862 5.862 0 0 1-4.671-2.381l-.66-.883-5.03-6.717a4.362 4.362 0 0 0-3.471-1.77H4.5zM14.862 8.567l.66-.883A5.862 5.862 0 0 1 20.193 5.3h1.057a.75.75 0 1 1 0 1.5h-1.057a4.362 4.362 0 0 0-3.471 1.768l-.66.883-.16-.214-.132-.176-.908-1.213-.01.014zM4.5 19.193a.75.75 0 1 0 0-1.5h1.057a4.362 4.362 0 0 0 3.471-1.768l.66-.883.908 1.213.14.186.124.166.01-.013.66.883A5.862 5.862 0 0 1 16.208 20.193H4.5z"></path>
                      </svg>
                  </button>
                  <button class="flex items-center justify-center w-8 h-8 rounded-full bg-transparent text-[#b3b3b3] hover:bg-[#282828] hover:text-white transition-all cursor-pointer" onclick={clearQueue} title="Lijst leegmaken">
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
</main>

{#if $activeModal}
  {#if $activeModal.type === 'search-results'}
    <SearchMoreModal query={$activeModal.data.query} category={$activeModal.data.category} />
  {/if}
{/if}

<style>
  :global(body) {
    margin: 0;
    padding: 0;
    overflow: hidden;
  }
</style>
