<script>
  import { createEventDispatcher, onMount } from 'svelte';
  import { currentTrack, playerState, audio, authParams, credentials, playlist } from './store.js';

  const dispatch = createEventDispatcher();

  let audioElement;

  let muted = false;
  let lastVolume = 50;

  function togglePlay() {
    if (!audioElement) return;
    if (audioElement.paused) {
      audioElement.play().catch(e => console.error("Playback failed", e));
    } else {
      audioElement.pause();
    }
  }

  function playNext() {
      const p = $playlist;
      if (p.length === 0) return;
      const currentIndex = p.findIndex(t => t.id === $currentTrack?.id);
      let nextIndex = currentIndex + 1;
      if (nextIndex >= p.length) {
          if ($playerState.repeat === 'all') {
              nextIndex = 0;
          } else {
              return;
          }
      }
      currentTrack.set(p[nextIndex]);
  }

  function playPrev() {
      const p = $playlist;
      if (p.length === 0) return;
      const currentIndex = p.findIndex(t => t.id === $currentTrack?.id);
      let prevIndex = currentIndex - 1;
      if (prevIndex < 0) {
          if ($playerState.repeat === 'all') {
              prevIndex = p.length - 1;
          } else {
              prevIndex = 0;
          }
      }
      currentTrack.set(p[prevIndex]);
  }

  function handleEnded() {
      if ($playerState.repeat === 'one') {
          audioElement.currentTime = 0;
          audioElement.play();
      } else {
          playNext();
      }
  }

  function toggleMute() {
    muted = !muted;
    if (muted) {
      lastVolume = $playerState.volume;
      audioElement.volume = 0;
    } else {
      audioElement.volume = lastVolume / 100;
    }
  }

  function handleTimeUpdate() {
    playerState.update(s => ({ ...s, progress: audioElement.currentTime }));
  }

  function handleLoadedMetadata() {
    playerState.update(s => ({ ...s, duration: audioElement.duration }));
  }

  function handlePlay() {
    playerState.update(s => ({ ...s, playing: true }));
  }

  function handlePause() {
    playerState.update(s => ({ ...s, playing: false }));
  }

  function handleVolumeChange() {
    playerState.update(s => ({ ...s, volume: audioElement.volume * 100 }));
  }

  function seek(e) {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const percentage = x / rect.width;
    audioElement.currentTime = percentage * audioElement.duration;
  }

  function changeVolume(e) {
      const rect = e.currentTarget.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const vol = Math.max(0, Math.min(1, x / rect.width));
      audioElement.volume = vol;
      muted = (vol === 0);
  }

  function formatTime(seconds) {
    if (isNaN(seconds)) return "0:00";
    const min = Math.floor(seconds / 60);
    const sec = Math.floor(seconds % 60);
    return `${min}:${sec < 10 ? '0' : ''}${sec}`;
  }

  function toggleRepeat() {
      playerState.update(s => {
          let next;
          if (s.repeat === 'none') next = 'all';
          else if (s.repeat === 'all') next = 'one';
          else next = 'none';
          return { ...s, repeat: next };
      });
  }

  function toggleShuffleMode() {
      playerState.update(s => ({ ...s, shuffle: !s.shuffle }));
  }

  $: track = $currentTrack;
  $: playing = $playerState.playing;
  $: progress = track ? $playerState.progress : 0;
  $: duration = track ? $playerState.duration : 0;
  $: volume = $playerState.volume;
  $: repeatMode = $playerState.repeat;
  $: shuffleMode = $playerState.shuffle;
  $: coverUrl = track?.coverArt ? `/rest/getCoverArt?id=${track.coverArt}&size=100&${$authParams}` : '/images/spotify-fallback.svg';
  $: streamUrl = track?.id ? `/rest/stream?id=${track.id}&${$authParams}` : '';

  let lastTrackId = null;
  $: if (audioElement && track && track.id !== lastTrackId) {
      lastTrackId = track.id;
      audioElement.src = streamUrl;
      audioElement.play().catch(e => {
          if (e.name !== 'AbortError') {
              console.error("Auto-play failed", e);
          }
      });
  }

  onMount(() => {
    audio.set(audioElement);
    audioElement.volume = volume / 100;
  });
</script>

<audio
  bind:this={audioElement}
  on:timeupdate={handleTimeUpdate}
  on:loadedmetadata={handleLoadedMetadata}
  on:play={handlePlay}
  on:pause={handlePause}
  on:volumechange={handleVolumeChange}
  on:ended={handleEnded}
></audio>

<footer class="player">
  <div class="current-track">
    {#if track}
      <img src={coverUrl} alt={track.title} on:error={(e) => e.target.src = '/images/spotify-fallback.svg'} />
      <div class="track-info">
        <div class="name">{track.title}</div>
        <div class="artist">{track.artist}</div>
      </div>
    {/if}
  </div>

  <div class="controls">
    <div class="buttons">
      <button class="shuffle" class:active={shuffleMode} on:click={toggleShuffleMode}>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <path d="M4.5 6.307a.75.75 0 1 1 0-1.5 5.862 5.862 0 0 1 4.671 2.382l.66.883 5.03 6.717a4.362 4.362 0 0 0 3.471 1.769h1.918a.75.75 0 1 1 0 1.5h-1.918a5.862 5.862 0 0 1-4.671-2.381l-.66-.883-5.03-6.717a4.362 4.362 0 0 0-3.471-1.77H4.5zM14.862 8.567l.66-.883A5.862 5.862 0 0 1 20.193 5.3h1.057a.75.75 0 1 1 0 1.5h-1.057a4.362 4.362 0 0 0-3.471 1.768l-.66.883-.16-.214-.132-.176-.908-1.213-.01.014zM4.5 19.193a.75.75 0 1 0 0-1.5h1.057a4.362 4.362 0 0 0 3.471-1.768l.66-.883.908 1.213.14.186.124.166.01-.013.66.883A5.862 5.862 0 0 1 16.208 20.193H4.5z"></path>
        </svg>
      </button>
      <button class="prev" on:click={playPrev}>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <path d="M11.838 12.767a1 1 0 0 0 0-1.534L4.513 5.32a.6.6 0 0 0-.913.434v12.492a.6.6 0 0 0 .913.434l7.325-5.913zM20.5 5.754a.6.6 0 0 0-.913-.434l-7.325 5.913a1 1 0 0 0 0 1.534l7.325 5.913a.6.6 0 0 0 .913-.434V5.754z"></path>
        </svg>
      </button>
      <button class="play-pause" on:click={togglePlay}>
        {#if playing}
            <svg viewBox="0 0 24 24" width="24" height="24" fill="black">
                <path d="M9 19H7V5h2v14zm8-14h-2v14h2V5z"></path>
            </svg>
        {:else}
            <svg viewBox="0 0 24 24" width="24" height="24" fill="black">
                <path d="M7 6v12l10-6z"></path>
            </svg>
        {/if}
      </button>
      <button class="next" on:click={playNext}>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <path d="M11.162 12.767a1 1 0 0 1 0-1.534l7.325-5.913a.6.6 0 0 1 .913.434v12.492a.6.6 0 0 1-.913.434l-7.325-5.913zM2.5 5.754a.6.6 0 0 1 .913-.434l7.325 5.913a1 1 0 0 1 0 1.534l-7.325 5.913a.6.6 0 0 1-.913-.434V5.754z"></path>
        </svg>
      </button>
      <button class="repeat" class:active={repeatMode !== 'none'} on:click={toggleRepeat}>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <path d="M4.5 12.2a.75.75 0 0 1 .75-.75h14a.75.75 0 0 1 .75.75v1.25a3.25 3.25 0 0 1-3.25 3.25H7.75a.75.75 0 0 1 0-1.5h8.25a1.75 1.75 0 0 0 1.75-1.75v-.5H5.25a.75.75 0 0 1-.75-.75v-1.25zM19.5 11.8a.75.75 0 0 1-.75.75h-14a.75.75 0 0 1-.75-.75v-1.25a3.25 3.25 0 0 1 3.25-3.25h8.5a.75.75 0 0 1 0 1.5h-8.5a1.75 1.75 0 0 0-1.75 1.75v.5h13.25a.75.75 0 0 1 .75.75v1.25z"></path>
        </svg>
        {#if repeatMode === 'one'}
            <span class="repeat-one">1</span>
        {/if}
      </button>
    </div>
    <div class="progress-bar">
      <span>{formatTime(progress)}</span>
      <div class="slider" on:click={seek}>
          <div class="fill" style="width: {(progress/duration)*100}%"></div>
      </div>
      <span>{formatTime(duration)}</span>
    </div>
  </div>

  <div class="volume">
    <button class="queue-btn" on:click={() => dispatch('toggleQueue')}>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <path d="M15 15H3v-1.5h12V15zm0-4.5H3V9h12v1.5zm0-4.5H3V4.5h12V6zm7 12l-4.5-4.5L13 18h9z"></path>
        </svg>
    </button>
    <button on:click={toggleMute}>
        {#if muted || volume === 0}
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                <path d="M16.107 2.493a.75.75 0 0 0-1.06 0l-7.057 7.057H2.25a.75.75 0 0 0-.75.75v3.314a.75.75 0 0 0 .75.75h5.74l7.057 7.057a.75.75 0 0 0 1.28-.53V3.023a.75.75 0 0 0-.22-.53zM14.607 18.66l-5.914-5.914a.75.75 0 0 0-.53-.22H3v-1.814h5.163a.75.75 0 0 0 .53-.22l5.914-5.914V18.66z"></path>
            </svg>
        {:else}
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                <path d="M12.944 3.32a.75.75 0 0 0-1.06 0L5.321 9.882H2.25a.75.75 0 0 0-.75.75v2.736a.75.75 0 0 0 .75.75h3.07l6.564 6.564a.75.75 0 0 0 1.06 0V3.32zM15.422 7.078a.75.75 0 0 1 1.06 0 7 7 0 0 1 0 9.9 1 1 0 0 1-1.06 0 .75.75 0 0 1 0-1.061 5.5 5.5 0 0 0 0-7.778.75.75 0 0 1 0-1.061z"></path>
            </svg>
        {/if}
    </button>
    <div class="volume-slider" on:click={changeVolume}>
        <div class="fill" style="width: {volume}%"></div>
    </div>
  </div>
</footer>

<style>
  .player {
    display: flex;
    justify-content: space-between;
    align-items: center;
    height: 100%;
    padding: 0 16px;
  }

  .current-track {
    width: 30%;
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .current-track img {
    width: 56px;
    height: 56px;
    border-radius: 4px;
  }

  .track-info .name {
    font-size: 14px;
    font-weight: 500;
  }

  .track-info .artist {
    font-size: 11px;
    color: #b3b3b3;
  }

  .controls {
    width: 40%;
    max-width: 600px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
  }

  .buttons {
    display: flex;
    align-items: center;
    gap: 24px;
  }

  button {
    background: none;
    border: none;
    color: #b3b3b3;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  button:hover {
    color: #fff;
  }

  button.active {
      color: #1db954;
  }

  .repeat {
      position: relative;
  }

  .repeat-one {
      position: absolute;
      font-size: 8px;
      font-weight: 700;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      color: #1db954;
      background-color: #181818;
      padding: 0 1px;
  }

  .play-pause {
    width: 32px;
    height: 32px;
    background-color: #fff;
    border-radius: 50%;
    color: #000;
  }

  .play-pause:hover {
    transform: scale(1.05);
    background-color: #f6f6f6;
  }

  .progress-bar {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    color: #b3b3b3;
  }

  .slider {
    flex: 1;
    height: 4px;
    background-color: #4d4d4d;
    border-radius: 2px;
  }

  .fill {
    height: 100%;
    width: 30%;
    background-color: #fff;
    border-radius: 2px;
  }

  .volume {
    width: 30%;
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 12px;
  }

  .queue-btn {
      margin-right: 8px;
  }

  .volume-slider {
    width: 100px;
    height: 4px;
    background-color: #4d4d4d;
    border-radius: 2px;
  }
</style>
