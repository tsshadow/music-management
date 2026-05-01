<script>
  import { onMount } from 'svelte';
  import Sidebar from './lib/Sidebar.svelte';
  import Player from './lib/Player.svelte';
  import Dashboard from './lib/Dashboard.svelte';
  import AuthOverlay from './lib/AuthOverlay.svelte';
  import { currentTrack, playerState } from './lib/store.js';

  let greeting = "";
  const hours = new Date().getHours();
  if (hours < 12) greeting = "Goedemorgen";
  else if (hours < 18) greeting = "Goedemiddag";
  else greeting = "Goedenavond";

  let activeView = 'home'; // 'home', 'songs', 'sets', 'playlists'

  function handleNavigate(view) {
    activeView = view;
  }
</script>

<main class="spotify-layout">
  <AuthOverlay />
  <div class="sidebar-container">
    <Sidebar {activeView} on:navigate={(e) => handleNavigate(e.detail)} />
  </div>
  
  <div class="main-view">
    <header>
      <h1>{greeting}</h1>
    </header>

    <div class="content-area">
      <Dashboard {activeView} />
    </div>
  </div>

  <div class="player-container">
    <Player />
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
    grid-template-columns: 240px 1fr;
    grid-template-rows: 1fr 90px;
    height: 100vh;
    width: 100vw;
  }

  .sidebar-container {
    background-color: #000;
    grid-row: 1 / 2;
  }

  .main-view {
    background: linear-gradient(to bottom, #121212, #121212);
    grid-row: 1 / 2;
    overflow-y: auto;
    padding: 20px 32px;
    position: relative;
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
