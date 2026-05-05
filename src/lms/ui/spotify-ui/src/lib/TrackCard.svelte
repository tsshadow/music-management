<script>
  import { currentTrack, playerState, authParams } from './store.js';
  import { createEventDispatcher } from 'svelte';
  import ArtistList from './ArtistList.svelte';

  const dispatch = createEventDispatcher();

  export let track;

  function play() {
    currentTrack.set(track);
    playerState.update(s => ({ ...s, playing: true }));
  }

  $: coverUrl = track.coverArt ? `/rest/getCoverArt?id=${track.coverArt}&size=300&${$authParams}` : '/images/spotify-fallback.svg';
</script>

<div class="card" on:click={play}>
  <div class="cover-wrapper">
    <img 
      src={coverUrl} 
      alt={track.title} 
      on:error={(e) => e.target.src = '/images/spotify-fallback.svg'}
    />
    <button class="play-btn">
      <svg viewBox="0 0 24 24" width="24" height="24" fill="black">
        <path d="M7 6v12l10-6z"></path>
      </svg>
    </button>
  </div>
  <div class="info">
    <span class="title">{track.title || track.name}</span>
    <ArtistList artist={track.artist} artistId={track.artistId} artists={track.artists} on:navigate />
  </div>
</div>

<style>
  .card {
    background-color: #181818;
    padding: 16px;
    border-radius: 8px;
    transition: background-color 0.3s;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .card:hover {
    background-color: #282828;
  }

  .cover-wrapper {
    position: relative;
    aspect-ratio: 1;
    box-shadow: 0 8px 24px rgba(0,0,0,0.5);
    border-radius: 4px;
    overflow: hidden;
  }

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .play-btn {
    position: absolute;
    right: 8px;
    bottom: 8px;
    width: 48px;
    height: 48px;
    background-color: #1db954;
    border: none;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 8px 16px rgba(0,0,0,0.3);
    opacity: 0;
    transform: translateY(8px);
    transition: all 0.3s;
  }

  .card:hover .play-btn {
    opacity: 1;
    transform: translateY(0);
  }

  .info {
    display: flex;
    flex-direction: column;
  }

  .title {
    font-size: 16px;
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .artist {
    font-size: 14px;
    color: #b3b3b3;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>
