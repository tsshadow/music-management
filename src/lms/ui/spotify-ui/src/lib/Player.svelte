<script>
  import { onMount } from 'svelte';
  import { currentTrack, playerState, audio, authParams, credentials, playlist, trackProgress, isMobile } from './store.js';
  import ArtistList from './ArtistList.svelte';

  const { onnavigate, ontoggleQueue } = $props();

  let audioElement;
  let muted = $state(false);
  let lastVolume = $state(50);

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
      if (!hasScrobbledFinished) {
          scrobble(true);
          hasScrobbledFinished = true;
      }
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
    updatePositionState();

    // Save progress periodically (every 5 seconds)
    const now = Date.now();
    if (track && now - lastProgressUpdate > 5000) {
      trackProgress.update(p => ({ ...p, [track.id]: audioElement.currentTime }));
      lastProgressUpdate = now;
    }

    if (!hasScrobbledFinished && track) {
        const threshold = Math.min(240, audioElement.duration / 2);
        if (audioElement.currentTime > threshold && audioElement.duration > 0) {
            scrobble(true);
            hasScrobbledFinished = true;
        }
    }
  }

  function handleLoadedMetadata() {
    playerState.update(s => ({ ...s, duration: audioElement.duration }));
    updatePositionState();
    if (!initialized && track) {
        // Restore progress if it exists for this track
        const savedProgress = $trackProgress[track.id];
        if (savedProgress) {
            audioElement.currentTime = savedProgress;
        } else {
            audioElement.currentTime = $playerState.progress || 0;
        }
        initialized = true;
    }
  }

  function handlePlay() {
    playerState.update(s => ({ ...s, playing: true }));
    if (!hasScrobbledStarted) {
        scrobble(false);
        hasScrobbledStarted = true;
    }
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

  function updatePositionState() {
    if ('mediaSession' in navigator &&
        'setPositionState' in navigator.mediaSession &&
        audioElement &&
        !isNaN(audioElement.duration) &&
        isFinite(audioElement.duration)) {
      try {
        navigator.mediaSession.setPositionState({
          duration: Math.max(0, audioElement.duration),
          playbackRate: audioElement.playbackRate || 1,
          position: Math.max(0, Math.min(audioElement.currentTime, audioElement.duration))
        });
      } catch (e) {
        console.error("Failed to set position state", e);
      }
    }
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

  const track = $derived($currentTrack);
  const playing = $derived($playerState.playing);
  const progress = $derived(track ? $playerState.progress : 0);
  const duration = $derived(track ? $playerState.duration : 0);
  const volume = $derived($playerState.volume);
  const repeatMode = $derived($playerState.repeat);
  const shuffleMode = $derived($playerState.shuffle);
  const coverUrl = $derived(track?.coverArt ? `/rest/getCoverArt?id=${track.coverArt}&size=100&${$authParams}` : '/images/spotify-fallback.svg');
  const streamUrl = $derived(track?.id ? `/rest/stream?id=${track.id}&${$authParams}` : '');

  $effect(() => {
    if (typeof navigator !== 'undefined' && 'mediaSession' in navigator && track) {
      const artUrl = track.coverArt
        ? `${$credentials.url}/rest/getCoverArt?id=${track.coverArt}&size=512&${$authParams}`
        : window.location.origin + '/images/spotify-fallback.svg';

      navigator.mediaSession.metadata = new MediaMetadata({
        title: track.title || 'Onbekend nummer',
        artist: track.artist || 'Onbekende artiest',
        album: track.album || 'Onbekend album',
        artwork: [
          { src: artUrl, sizes: '512x512', type: 'image/jpeg' }
        ]
      });
    }
  });

  $effect(() => {
    if (typeof navigator !== 'undefined' && 'mediaSession' in navigator) {
      navigator.mediaSession.playbackState = playing ? 'playing' : 'paused';
    }
  });

  let lastProgressUpdate = 0;
  let lastTrackId = null;
  let hasScrobbledStarted = false;
  let hasScrobbledFinished = false;
  let initialized = false;

  async function scrobble(submission = true) {
    if (!track || !$credentials.username) return;
    const params = $authParams;
    const url = `${$credentials.url}/rest/scrobble?id=${track.id}&submission=${submission}&${params}`;
    try {
      await fetch(url);
    } catch (e) {
      console.error("Scrobble failed", e);
    }
  }

  $effect(() => {
    if (track && track.id !== lastTrackId) {
        const isInitialLoad = !lastTrackId && !initialized;
        lastTrackId = track.id;
        hasScrobbledStarted = false;
        hasScrobbledFinished = false;
        if (audioElement) {
            audioElement.src = streamUrl;
            if (!isInitialLoad) {
                // Check if we have saved progress for this track
                const savedProgress = $trackProgress[track.id];
                if (savedProgress) {
                    audioElement.currentTime = savedProgress;
                }
                
                audioElement.play().catch(e => {
                    if (e.name !== 'AbortError') {
                        console.error("Auto-play failed", e);
                    }
                });
            }
        }
    }
  });

  onMount(() => {
    audio.set(audioElement);
    audioElement.volume = volume / 100;

    if (track && !initialized) {
        audioElement.src = streamUrl;
        // currentTime will be set in handleLoadedMetadata
    }

    if (typeof navigator !== 'undefined' && 'mediaSession' in navigator) {
      navigator.mediaSession.setActionHandler('play', () => togglePlay());
      navigator.mediaSession.setActionHandler('pause', () => togglePlay());
      navigator.mediaSession.setActionHandler('previoustrack', () => playPrev());
      navigator.mediaSession.setActionHandler('nexttrack', () => playNext());
      try {
        navigator.mediaSession.setActionHandler('seekto', (details) => {
          if (details.seekTime !== undefined && audioElement) {
            audioElement.currentTime = details.seekTime;
          }
        });
      } catch (e) {
        console.warn("MediaSession seekto not supported", e);
      }
    }
  });
</script>

<audio
  bind:this={audioElement}
  ontimeupdate={handleTimeUpdate}
  onloadedmetadata={handleLoadedMetadata}
  onplay={handlePlay}
  onpause={handlePause}
  onvolumechange={handleVolumeChange}
  onended={handleEnded}
></audio>

<footer class="flex items-center h-full px-2 md:px-4 relative">
  {#if $isMobile}
    <!-- Mobile Mini Player -->
    <div class="flex flex-1 items-center gap-3 min-w-0 py-2 h-full">
      {#if track}
        <img src={coverUrl} alt={track.title} class="w-11 h-11 rounded shadow-lg" onerror={(e) => e.target.src = '/images/spotify-fallback.svg'} />
        <div class="flex-1 min-w-0">
          <div class="text-[13px] font-bold text-white truncate">{track.title}</div>
          <div class="text-[11px] text-[#b3b3b3] truncate">{track.artist}</div>
        </div>
      {:else}
        <div class="flex-1 flex items-center gap-3 min-w-0">
          <div class="w-11 h-11 bg-white/5 rounded flex items-center justify-center">
            <svg viewBox="0 0 24 24" width="24" height="24" fill="#535353">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 14.5c-2.49 0-4.5-2.01-4.5-4.5S9.51 7.5 12 7.5s4.5 2.01 4.5 4.5-2.01 4.5-4.5 4.5zm0-7c-1.38 0-2.5 1.12-2.5 2.5s1.12 2.5 2.5 2.5 2.5-1.12 2.5-2.5-1.12-2.5-2.5-2.5z"></path>
            </svg>
          </div>
          <div class="text-[13px] text-[#b3b3b3] italic font-medium">Niets aan het afspelen</div>
        </div>
      {/if}
      <div class="flex items-center gap-4 px-2">
        <button class="bg-transparent border-none p-0 text-white" onclick={togglePlay} aria-label={playing ? "Pauze" : "Afspelen"}>
          {#if playing}
            <svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor">
              <path d="M9 19H7V5h2v14zm8-14h-2v14h2V5z"></path>
            </svg>
          {:else}
            <svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor">
              <path d="M7 6v12l10-6z"></path>
            </svg>
          {/if}
        </button>
      </div>
    </div>
    <!-- Progress bar for mobile -->
    {#if track}
      <div class="absolute top-0 left-0 w-full h-[2px] bg-white/10">
        <div class="h-full bg-white transition-all duration-100" style="width: {(progress/duration)*100}%"></div>
      </div>
    {/if}
  {:else}
    <!-- Desktop Player -->
    <div class="w-[30%] hidden md:flex items-center gap-3">
      {#if track}
        <img src={coverUrl} alt={track.title} class="w-14 h-14 rounded" onerror={(e) => e.target.src = '/images/spotify-fallback.svg'} />
        <div class="track-info min-w-0">
          <div class="text-sm font-medium truncate">{track.title}</div>
          <ArtistList 
            artist={track.artist} 
            artistId={track.artistId} 
            artists={track.artists} 
            onnavigate={onnavigate} 
          />
        </div>
      {/if}
    </div>

    <div class="flex-1 md:w-[40%] max-w-[600px] flex flex-col items-center gap-2">
      <div class="flex items-center gap-4 md:gap-6">
        <button class="hidden md:flex bg-transparent border-none p-0 items-center justify-center cursor-pointer transition-colors hover:text-white {shuffleMode ? 'text-spotify-green' : 'text-[#b3b3b3]'}" onclick={toggleShuffleMode} aria-label="Shuffle">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
              <path d="M4.5 6.307a.75.75 0 1 1 0-1.5 5.862 5.862 0 0 1 4.671 2.382l.66.883 5.03 6.717a4.362 4.362 0 0 0 3.471 1.769h1.918a.75.75 0 1 1 0 1.5h-1.918a5.862 5.862 0 0 1-4.671-2.381l-.66-.883-5.03-6.717a4.362 4.362 0 0 0-3.471-1.77H4.5zM14.862 8.567l.66-.883A5.862 5.862 0 0 1 20.193 5.3h1.057a.75.75 0 1 1 0 1.5h-1.057a4.362 4.362 0 0 0-3.471 1.768l-.66.883-.16-.214-.132-.176-.908-1.213-.01.014zM4.5 19.193a.75.75 0 1 0 0-1.5h1.057a4.362 4.362 0 0 0 3.471-1.768l.66-.883.908 1.213.14.186.124.166.01-.013.66.883A5.862 5.862 0 0 1 16.208 20.193H4.5z"></path>
          </svg>
        </button>
        <button class="bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors hover:text-white text-[#b3b3b3]" onclick={playPrev} aria-label="Vorige">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
              <path d="M11.838 12.767a1 1 0 0 0 0-1.534L4.513 5.32a.6.6 0 0 0-.913.434v12.492a.6.6 0 0 0 .913.434l7.325-5.913zM20.5 5.754a.6.6 0 0 0-.913-.434l-7.325 5.913a1 1 0 0 0 0 1.534l7.325 5.913a.6.6 0 0 0 .913-.434V5.754z"></path>
          </svg>
        </button>
        <button class="w-8 h-8 bg-white rounded-full text-black flex items-center justify-center cursor-pointer transition-transform hover:scale-105" onclick={togglePlay}>
          {#if playing}
              <svg viewBox="0 0 24 24" width="20" height="20" fill="black">
                  <path d="M9 19H7V5h2v14zm8-14h-2v14h2V5z"></path>
              </svg>
          {:else}
              <svg viewBox="0 0 24 24" width="20" height="20" fill="black">
                  <path d="M7 6v12l10-6z"></path>
              </svg>
          {/if}
        </button>
        <button class="bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors hover:text-white text-[#b3b3b3]" onclick={playNext} aria-label="Volgende">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
              <path d="M11.162 12.767a1 1 0 0 1 0-1.534l7.325-5.913a.6.6 0 0 1 .913.434v12.492a.6.6 0 0 1-.913.434l-7.325-5.913zM2.5 5.754a.6.6 0 0 1 .913-.434l7.325 5.913a1 1 0 0 1 0 1.534l-7.325 5.913a.6.6 0 0 1-.913-.434V5.754z"></path>
          </svg>
        </button>
        <button class="hidden md:flex relative bg-transparent border-none p-0 items-center justify-center cursor-pointer transition-colors hover:text-white {repeatMode !== 'none' ? 'text-spotify-green' : 'text-[#b3b3b3]'}" onclick={toggleRepeat} aria-label="Herhalen">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
              <path d="M4.5 12.2a.75.75 0 0 1 .75-.75h14a.75.75 0 0 1 .75.75v1.25a3.25 3.25 0 0 1-3.25 3.25H7.75a.75.75 0 0 1 0-1.5h8.25a1.75 1.75 0 0 0 1.75-1.75v-.5H5.25a.75.75 0 0 1-.75-.75v-1.25zM19.5 11.8a.75.75 0 0 1-.75.75h-14a.75.75 0 0 1-.75-.75v-1.25a3.25 3.25 0 0 1 3.25-3.25h8.5a.75.75 0 0 1 0 1.5h-8.5a1.75 1.75 0 0 0-1.75 1.75v.5h13.25a.75.75 0 0 1 .75.75v1.25z"></path>
          </svg>
          {#if repeatMode === 'one'}
              <span class="absolute text-[8px] font-bold top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-spotify-green bg-[#181818] px-[1px]">1</span>
          {/if}
        </button>
      </div>
      <div class="hidden md:flex w-full items-center gap-2 text-[11px] text-[#b3b3b3]">
        <span>{formatTime(progress)}</span>
        <div 
          role="button"
          tabindex="0"
          class="flex-1 h-1 bg-[#4d4d4d] rounded-sm cursor-pointer" 
          onclick={seek}
          onkeydown={(e) => e.key === 'Enter' && seek(e)}
          aria-label="Seek track"
        >
            <div class="h-full bg-white rounded-sm" style="width: {(progress/duration)*100}%"></div>
        </div>
        <span>{formatTime(duration)}</span>
      </div>
    </div>

    <div class="w-[30%] hidden md:flex justify-end items-center gap-3">
      <button class="mr-2 bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors hover:text-white text-[#b3b3b3]" onclick={ontoggleQueue} aria-label="Wachtrij">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
              <path d="M15 15H3v-1.5h12V15zm0-4.5H3V9h12v1.5zm0-4.5H3V4.5h12V6zm7 12l-4.5-4.5L13 18h9z"></path>
          </svg>
      </button>
      <button class="bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors hover:text-white text-[#b3b3b3]" onclick={toggleMute}>
          {#if muted || volume === 0}
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                  <path d="M16.107 2.493a.75.75 0 0 0-1.06 0l-7.057 7.057H2.25a.75.75 0 0 0-.75.75v3.314a.75.75 0 0 0 .75.75h5.74l7.057 7.057a.75.75 0 0 0 1.28-.53V3.023a.75.75 0 0 0-.22-.53zM14.607 18.66l-5.914-5.914a.75.75 0 0 0-.53-.22H3v-1.814h5.163a.75.75 0 0 0 .53-.22l5.914-5.914V18.66z"></path>
              </svg>
          {:else}
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                  <path d="M15.545 1.488a.75.75 0 0 1 .103 1.055C18.106 5.54 19.5 9.1 19.5 13s-1.394 7.46-3.852 10.457a.75.75 0 1 1-1.154-.959C16.634 19.863 18 16.594 18 13c0-3.594-1.366-6.863-3.507-9.458a.75.75 0 0 1 .103-1.054zm-2.81 3.23a.75.75 0 0 1 .102 1.054C14.346 7.41 15 10.124 15 13c0 2.876-.654 5.59-2.163 7.228a.75.75 0 1 1-1.155-.958C13.065 17.518 13.5 15.308 13.5 13c0-2.308-.435-4.518-1.838-6.228a.75.75 0 0 1 .103-1.054zM9.548 8.016a.75.75 0 0 1 .103 1.054C10.222 9.8 10.5 11.371 10.5 13c0 1.629-.278 3.2-.849 3.93a.75.75 0 1 1-1.155-.958c.321-.386.504-1.516.504-2.972 0-1.456-.183-2.586-.504-2.972a.75.75 0 0 1 .103-1.054z"></path>
              </svg>
          {/if}
      </button>
      <div 
        role="button"
        tabindex="0"
        class="w-24 h-1 bg-[#4d4d4d] rounded-sm cursor-pointer" 
        onclick={changeVolume}
        onkeydown={(e) => e.key === 'Enter' && changeVolume(e)}
        aria-label="Volume"
      >
        <div class="h-full bg-white rounded-sm" style="width: {volume}%"></div>
      </div>
    </div>
  {/if}
</footer>

<style>
</style>
