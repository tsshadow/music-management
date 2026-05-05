<script>
  import { onMount } from 'svelte';
  import Sidebar from './lib/Sidebar.svelte';
  import Player from './lib/Player.svelte';
  import Dashboard from './lib/Dashboard.svelte';
  import AuthOverlay from './lib/AuthOverlay.svelte';
  import TrackList from './lib/TrackList.svelte';
  import { currentTrack, playerState, playlist, activeView } from './lib/store.js';

  let greeting = "";
  const hours = new Date().getHours();
  if (hours < 12) greeting = "Goedemorgen";
  else if (hours < 18) greeting = "Goedemiddag";
  else greeting = "Goedenavond";

  let showQueue = false;

  function handleNavigate(view) {
    activeView.set(view);
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

<main class="spotify-layout">
  <AuthOverlay />
  <div class="sidebar-container">
    <Sidebar activeView={$activeView} on:navigate={(e) => handleNavigate(e.detail)} />
  </div>
  
  <div class="main-view">
    <header>
      <h1>{greeting}</h1>
    </header>

    <div class="content-area">
      <Dashboard bind:activeView={$activeView} />
    </div>
  </div>

  <div class="queue-view" class:hidden={!showQueue}>
      <header>
          <h2>Wachtrij</h2>
          <div class="actions">
              <button class="action-btn" on:click={shuffleQueue} title="Shuffle">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                      <path d="M4.5 6.307a.75.75 0 1 1 0-1.5 5.862 5.862 0 0 1 4.671 2.382l.66.883 5.03 6.717a4.362 4.362 0 0 0 3.471 1.769h1.918a.75.75 0 1 1 0 1.5h-1.918a5.862 5.862 0 0 1-4.671-2.381l-.66-.883-5.03-6.717a4.362 4.362 0 0 0-3.471-1.77H4.5zM14.862 8.567l.66-.883A5.862 5.862 0 0 1 20.193 5.3h1.057a.75.75 0 1 1 0 1.5h-1.057a4.362 4.362 0 0 0-3.471 1.768l-.66.883-.16-.214-.132-.176-.908-1.213-.01.014zM4.5 19.193a.75.75 0 1 0 0-1.5h1.057a4.362 4.362 0 0 0 3.471-1.768l.66-.883.908 1.213.14.186.124.166.01-.013.66.883A5.862 5.862 0 0 1 16.208 20.193H4.5z"></path>
                  </svg>
              </button>
              <button class="action-btn" on:click={clearQueue} title="Lijst leegmaken">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                      <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"></path>
                  </svg>
              </button>
              <button class="close-btn" on:click={() => showQueue = false}>&times;</button>
          </div>
      </header>
      <TrackList tracks={$playlist} isQueue={true} on:navigate={(e) => activeView.set(e.detail)} />
  </div>

  <div class="player-container">
    <Player on:toggleQueue={() => showQueue = !showQueue} />
  </div>
</main>

<style>
  :global(body) {
    margin: 0;
    padding: 0;
    background-color: #000;
    color: #fff;
    font-family: 'Circular Std', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
    overflow: hidden;
  }

  .spotify-layout {
    display: grid;
    grid-template-columns: 240px 1fr auto;
    grid-template-rows: 1fr 90px;
    height: 100vh;
    width: 100vw;
  }

  .sidebar-container {
    background-color: #000;
    grid-row: 1 / 2;
    grid-column: 1 / 2;
  }

  .main-view {
    background: linear-gradient(to bottom, #121212, #121212);
    grid-row: 1 / 2;
    grid-column: 2 / 3;
    overflow-y: auto;
    padding: 20px 32px;
    position: relative;
  }

  .queue-view {
      background-color: #121212;
      grid-row: 1 / 2;
      grid-column: 3 / 4;
      width: 350px;
      border-left: 1px solid #282828;
      overflow-y: auto;
      padding: 20px;
  }

  .queue-view.hidden {
      display: none;
  }

  .queue-view header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
  }

  .queue-view header h2 {
      font-size: 18px;
      margin: 0;
  }

  .queue-view header button {
      background: none;
      border: none;
      color: #b3b3b3;
      font-size: 24px;
      cursor: pointer;
  }

  .actions {
      display: flex;
      align-items: center;
      gap: 12px;
  }

  .action-btn {
      display: flex !important;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      border-radius: 50%;
      background-color: transparent;
      color: #b3b3b3 !important;
      font-size: 16px !important;
      transition: all 0.2s;
  }

  .action-btn:hover {
      background-color: #282828;
      color: #fff !important;
  }

  .close-btn {
      font-size: 24px !important;
      padding: 0 8px;
  }

  header {
    margin-bottom: 24px;
  }

  h1 {
    font-size: 32px;
    font-weight: 700;
  }

  .player-container {
    background-color: #181818;
    grid-column: 1 / 3;
    grid-row: 2 / 3;
    border-top: 1px solid #282828;
  }

  .content-area {
    padding-bottom: 32px;
  }
</style>
