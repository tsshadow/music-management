<script>
  import { t } from './i18n/index.js';
  import { onMount } from 'svelte';
  import { currentTrack, playerState, audio, authParams, credentials, playlist, isMobile, syncMode, highlightedTrackId, activeView, radioChannel, radioNowPlaying, mumaApiUrl, mumaApiKey, equalizerSettings } from './store.js';
  import Equalizer from './Equalizer.svelte';
  import * as equalizer from './equalizer.js';
  import { createRadioController } from './radioController.js';
  import { shouldPushJamState } from './radioSync.js';
  import { resolveDuration, progressPercent } from './playerProgress.js';
  import { describeFilter } from './management/radioChannels.js';
  import { snapshotOf, restoreTarget, bulletinStreamUrl } from './newsQueue.js';
  import { startTrail, stepBack, stepForward } from './shuffleHistory.js';
  import ArtistList from './ArtistList.svelte';
  import { getArtistImageUrl, subsonicError } from './utils.js';
  import { getHeaders } from './mumaApi.js';
  import { notify } from './notifications.js';

  const { onnavigate, ontoggleQueue } = $props();

  let audioElement;
  let muted = $state(false);
  let lastVolume = $state(50);
  let lastSyncTime = null;
  let lastPushTime = 0;
  let isSyncing = false;

  let radioController = null;
  let radioTickInterval = null;
  let radioRefreshInterval = null;
  let radioClockInterval = null;
  let progressTicker = null;
  let radioChannels = $state([]);
  // Set while a news bulletin is interrupting the music, and holding what to
  // put back when it ends.
  let newsSnapshot = $state(null);
  let newsObjectUrl = null;
  let showRadioPicker = $state(false);

  let showEqualizer = $state(false);
  let equalizerPanelEl = $state(null);
  let equalizerButtonEl = $state(null);
  const equalizerSupported = equalizer.isSupported();

  /**
   * Closes the panel on a click elsewhere.
   *
   * The toggle button has to be excluded as well as the panel: on mobile the
   * button sits in the mini player and the sheet is a separate fixed element,
   * so without this check the button's own click would close the sheet again
   * the instant its handler opened it.
   */
  function closeEqualizerOnOutsideClick(event) {
    if (equalizerPanelEl?.contains(event.target)) return;
    if (equalizerButtonEl?.contains(event.target)) return;
    showEqualizer = false;
  }

  $effect(() => {
    if (!showEqualizer) return;
    window.addEventListener('click', closeEqualizerOnOutsideClick);
    return () => window.removeEventListener('click', closeEqualizerOnOutsideClick);
  });

  // The one place settings reach the audio graph. Attaching happens lazily,
  // on the first switch-on: that is always a user gesture, which is what the
  // browser demands before an AudioContext may start.
  $effect(() => {
    const settings = $equalizerSettings;
    if (!settings.enabled) {
      equalizer.setEnabled(false);
      return;
    }
    if (!equalizer.attach(audioElement)) return;
    equalizer.setGains(settings.gains);
    equalizer.setPreamp(settings.preamp);
    equalizer.setEnabled(true);
  });

  /**
   * Builds a stream URL for radio playback. `format=mp3` is required: LMS only
   * honours `timeOffset` on the transcoding path (MediaRetrieval.cpp:146-147).
   *
   * @param {string} trackId
   * @param {number} offsetSeconds
   * @returns {string}
   */
  function radioStreamUrl(trackId, offsetSeconds) {
    return `${$credentials.url}/rest/stream?id=${trackId}&format=mp3&maxBitRate=320&timeOffset=${offsetSeconds}&${$authParams}`;
  }

  /**
   * Switches radio off, or offers the channels on air. With one channel there is
   * nothing to choose, so it starts straight away.
   */
  async function toggleRadio() {
    if ($radioChannel) {
      radioController?.stop();
      clearInterval(radioTickInterval);
      clearInterval(radioRefreshInterval);
      clearInterval(radioClockInterval);
      radioTickInterval = null;
      radioRefreshInterval = null;
      radioClockInterval = null;
      radioController = null;
      radioChannel.set(null);
      radioNowPlaying.set(null);
      showRadioPicker = false;
      return;
    }

    if (showRadioPicker) {
      showRadioPicker = false;
      return;
    }

    try {
      const response = await fetch(`${$mumaApiUrl}/api/radio/channels`, {
        headers: { 'X-API-Key': $mumaApiKey },
      });
      const body = await response.json();
      radioChannels = body.channels || [];
      if (!radioChannels.length) {
        console.warn($t('radio.noChannels'));
        return;
      }
      if (radioChannels.length === 1) {
        await startRadio(radioChannels[0]);
        return;
      }
      showRadioPicker = true;
    } catch (e) {
      console.error($t('radio.couldNotStart'), e);
    }
  }

  /**
   * Tunes into one channel. Requires a user gesture, which is exactly why this
   * runs from a click handler: starting playback from a timer would be blocked
   * by browser autoplay policy.
   *
   * @param {{slug: string}} channel
   */
  async function startRadio(channel) {
    showRadioPicker = false;
    try {
      radioController = createRadioController({
        audio: audioElement,
        apiBase: $mumaApiUrl,
        apiKey: $mumaApiKey,
        streamUrlFor: radioStreamUrl,
      });
      await radioController.start(channel.slug);
      radioChannel.set(channel.slug);
      radioNowPlaying.set(radioController.getEntry());

      radioTickInterval = setInterval(() => radioController?.tick(), 2000);
      radioRefreshInterval = setInterval(async () => {
        await radioController?.refresh();
        radioNowPlaying.set(radioController?.getEntry() ?? null);
      }, 10000);
      // Clocks drift over a long listening session, so re-measure now and then.
      radioClockInterval = setInterval(() => radioController?.measureClockOffset(), 300000);
    } catch (e) {
      console.error($t('radio.couldNotStart'), e);
    }
  }

  /**
   * Plays the most recent bulletin, or gives the music back if one is running.
   *
   * The audio element cannot send an `X-API-Key` header, and the endpoint takes
   * the key no other way, so the bulletin is fetched and played from a blob.
   * A ten-minute recording is around 14 MB, which is a short wait on a LAN and
   * buys the same authentication the rest of the app uses.
   */
  async function toggleNews() {
    if (newsSnapshot) {
      await stopNews();
      return;
    }
    try {
      const headers = getHeaders();
      const response = await fetch(`${$mumaApiUrl}/api/news/bulletins/latest`, { headers });
      // Only a 404 means what the message says. Every other status is the hop
      // failing -- an expired key, the proxy's concurrency gate, a bulletin too
      // large for it -- and calling that "nothing recorded yet" sent every reader
      // looking at the recorder, which was working the whole time.
      if (!response.ok) {
        if (response.status === 404) notify.error($t('news.none'));
        else notify.error($t('news.couldNotPlay'), { detail: `HTTP ${response.status}` });
        return;
      }
      const bulletin = await response.json();
      const audioResponse = await fetch(bulletinStreamUrl($mumaApiUrl, bulletin.id), { headers });
      if (!audioResponse.ok) {
        notify.error($t('news.couldNotPlay'), { detail: `HTTP ${audioResponse.status}` });
        return;
      }
      const blob = await audioResponse.blob();

      newsSnapshot = snapshotOf({
        trackId: $radioChannel ? null : (track?.id ?? null),
        positionSeconds: audioElement?.currentTime ?? 0,
        radioChannel: $radioChannel,
      });
      // Radio has to be switched off rather than paused: it drives the same
      // element, and it would keep correcting the bulletin's position.
      if ($radioChannel) await toggleRadio();

      newsObjectUrl = URL.createObjectURL(blob);
      audioElement.src = newsObjectUrl;
      await audioElement.play();
    } catch (e) {
      console.error('Could not play the news', e);
      notify.error($t('news.couldNotPlay'), { detail: e.message });
    }
  }

  /** Ends the bulletin and resumes whatever it interrupted. */
  async function stopNews() {
    const target = restoreTarget(newsSnapshot);
    newsSnapshot = null;
    if (newsObjectUrl) {
      URL.revokeObjectURL(newsObjectUrl);
      newsObjectUrl = null;
    }

    if (target.action === 'retune') {
      await startRadio({ slug: target.channel });
      return;
    }
    if (target.action === 'none') {
      audioElement.pause();
      audioElement.removeAttribute('src');
      return;
    }

    audioElement.src = streamUrl;
    audioElement.currentTime = target.positionSeconds;
    try {
      await audioElement.play();
    } catch (e) {
      if (e.name !== 'AbortError') console.error('Could not resume after the news', e);
    }
  }

  /**
   * Sends the current player state to the server if sync mode is active.
   * 
   * @param {boolean|null} overridePlaying - Optional override for the playing state.
   * @param {string|null} overrideTrackId - Optional override for the current track ID.
   */
  async function pushJamState(overridePlaying = null, overrideTrackId = null) {
    if ($syncMode === 'off' || isSyncing || !$credentials.username) return;
    lastPushTime = Date.now();
    try {
        const params = $authParams;
        const trackIds = $playlist.map(t => `id=${t.id}`).join('&');
        
        // Use overrides if provided, otherwise use local state
        const currentId = overrideTrackId !== null ? overrideTrackId : ($currentTrack?.id || '');
        const isPlaying = overridePlaying !== null ? overridePlaying : (audioElement ? !audioElement.paused : false);
        const position = audioElement ? Math.floor(audioElement.currentTime * 1000) : 0;

        // In follower mode, we NEVER push periodic position to avoid fighting the host.
        // The 'position' parameter is only included if we are the Host.
        let url = `${$credentials.url}/rest/savePlayQueue?${trackIds}&current=${currentId}&playing=${isPlaying}&${params}`;
        if ($syncMode === 'host') {
            url += `&position=${position}`;
        }

        await fetch(url);
    } catch (e) {
        console.error("Jam push failed", e);
    }
  }

  /**
   * Fetches the player state from the server and synchronizes the local player.
   */
  async function syncJam() {
    if ($syncMode === 'off' || isSyncing || !$credentials.username || !audioElement) return;

    // Don't sync from server if we just pushed our own state (within last 5 seconds)
    // to avoid "jumps" caused by server having slightly outdated state.
    if (Date.now() - lastPushTime < 5000) return;

    isSyncing = true;
    try {
      const params = $authParams;
      const response = await fetch(`${$credentials.url}/rest/getPlayQueue?${params}`);
      const data = await response.json();
      const playQueue = data['subsonic-response']?.playQueue;

      if (playQueue) {
        const serverChanged = playQueue.changed;
        if (serverChanged !== lastSyncTime) {
          if (playQueue.entry) {
            const tracks = Array.isArray(playQueue.entry) ? playQueue.entry : [playQueue.entry];

            // Sync playlist
            if (JSON.stringify(tracks.map(t => t.id)) !== JSON.stringify($playlist.map(t => t.id))) {
                playlist.set(tracks);
            }

            // Sync current track
            const currentTrackId = playQueue.current;
            const serverTrack = tracks.find(t => t.id === currentTrackId);
            const trackChanged = serverTrack && String($currentTrack?.id) !== String(serverTrack.id);

            const serverPlaying = playQueue.playing === "true" || playQueue.playing === true;
            const playingChanged = serverPlaying !== !audioElement.paused;

            // HOST LOGIC: Only apply changes if the server state is different from local
            // (indicating a remote command from a Follower)
            if ($syncMode === 'host') {
                if (trackChanged || playingChanged) {
                    if (trackChanged) currentTrack.set(serverTrack);
                    if (playingChanged) {
                        if (serverPlaying) audioElement.play().catch(() => {});
                        else audioElement.pause();
                    }
                }
                lastSyncTime = serverChanged;
                return;
            }

            // JAM FOLLOWER LOGIC: Remote control, no local audio
            if ($syncMode === 'follower-jam') {
                if (trackChanged) {
                    currentTrack.set(serverTrack);
                }
                // Update local playing state store so UI reflects host state
                playerState.update(s => ({ ...s, playing: serverPlaying }));
                
                // Ensure audio is stopped
                if (!audioElement.paused) {
                    audioElement.pause();
                }
                lastSyncTime = serverChanged;
                return;
            }

            // RADIO FOLLOWER LOGIC: Apply everything from server (Listen along)
            if (trackChanged) {
                currentTrack.set(serverTrack);
            }

            const serverPos = (playQueue.position || 0) / 1000;

            // Sync position if difference > 5 seconds
            if (Math.abs(audioElement.currentTime - serverPos) > 5) {
                audioElement.currentTime = serverPos;
            }

            // Sync play/pause
            if (serverPlaying && audioElement.paused) {
                audioElement.play().catch(() => {});
            } else if (!serverPlaying && !audioElement.paused) {
                audioElement.pause();
            }

            lastSyncTime = serverChanged;
          }
        }
      }
    } catch (e) {
      console.error("Jam sync failed", e);
    } finally {
      isSyncing = false;
    }
  }

  /**
   * Toggles between play and pause states.
   */
  function togglePlay() {
    if (!audioElement) return;

    if ($syncMode === 'follower-jam') {
        // Remote control: toggle the state reported by the server
        pushJamState(!$playerState.playing);
        return;
    }

    if (audioElement.paused) {
      audioElement.play().catch(e => {
        console.error("Playback failed", e);
        notify.error($t('notify.playbackFailed'), { detail: e.message });
      });
    } else {
      audioElement.pause();
    }
    if ($syncMode !== 'off') {
      pushJamState();
    }
  }

  // Where shuffle play has been. It is not in `playerState` because nothing outside
  // this component reads it and it must not survive a reload as a list of ids that
  // the restored queue may no longer contain.
  let shuffleTrail = $state(startTrail(null));

  /**
   * The trail to step through, restarted when it has lost touch with the queue.
   *
   * A queue swap or a track picked straight out of the list leaves the trail pointing
   * at something else entirely; carrying on from there would send "previous" to a
   * track the listener never played.
   *
   * @param {Array} queue - The tracks in the queue.
   * @param {string|null} playingId - Id of the track playing now.
   * @returns {{ids: string[], position: number}} The trail to use.
   */
  function trailFor(queue, playingId) {
      const known = new Set(queue.map(track => String(track.id)));
      const onTrack = shuffleTrail.ids[shuffleTrail.position] === playingId;
      const intact = shuffleTrail.ids.every(id => known.has(id));
      return onTrack && intact ? shuffleTrail : startTrail(playingId);
  }

  /**
   * Plays the next track in the playlist.
   * Handles shuffle and repeat logic.
   */
  function playNext() {
      const p = $playlist;
      if (p.length === 0) return;
      const currentTrackId = $currentTrack ? String($currentTrack.id) : null;
      const currentIndex = p.findIndex(t => String(t.id) === currentTrackId);

      let nextIndex;
      if ($playerState.shuffle) {
          // Walk the trail rather than drawing blind, so a previous followed by a
          // next lands back on the track it came from instead of a third one.
          const stepped = stepForward(trailFor(p, currentTrackId), p.map(t => String(t.id)));
          shuffleTrail = stepped.trail;
          nextIndex = p.findIndex(t => String(t.id) === stepped.id);
          if (nextIndex < 0) return;
      } else {
          nextIndex = currentIndex + 1;
          if (nextIndex >= p.length) {
              if ($playerState.repeat === 'all') {
                  nextIndex = 0;
              } else {
                  return;
              }
          }
      }

      const nextTrack = p[nextIndex];
      if (nextTrack) {
          if ($syncMode === 'follower-jam') {
              // Remote control: send intent to play next track
              pushJamState(true, nextTrack.id);
              return;
          }

          // If it's the same track (e.g. single track playlist), restart it manually
          // because the $effect that watches currentTrack might not trigger on same ID
          if (String($currentTrack?.id) === String(nextTrack.id) && audioElement) {
              audioElement.currentTime = 0;
              audioElement.play().catch(() => {});
          }
          currentTrack.set(nextTrack);
      }
      if ($syncMode !== 'off') {
        pushJamState();
      }
  }

  /**
   * Plays the previous track in the playlist.
   * Restarts the current track if it has played for more than 3 seconds.
   * Handles shuffle and repeat logic.
   */
  function playPrev() {
      // If more than 3 seconds into the track, restart it
      if (audioElement && audioElement.currentTime > 3) {
          audioElement.currentTime = 0;
          return;
      }

      const p = $playlist;
      if (p.length === 0) return;
      const currentTrackId = $currentTrack ? String($currentTrack.id) : null;
      const currentIndex = p.findIndex(t => String(t.id) === currentTrackId);

      let prevIndex;
      if ($playerState.shuffle) {
          const stepped = stepBack(trailFor(p, currentTrackId));
          shuffleTrail = stepped.trail;
          prevIndex = p.findIndex(t => String(t.id) === stepped.id);
          if (prevIndex < 0) return;
      } else {
          prevIndex = currentIndex - 1;
          if (prevIndex < 0) {
              if ($playerState.repeat === 'all') {
                  prevIndex = p.length - 1;
              } else {
                  prevIndex = 0;
              }
          }
      }

      const prevTrack = p[prevIndex];
      if (prevTrack) {
          if ($syncMode === 'follower-jam') {
              // Remote control: send intent to play previous track
              pushJamState(true, prevTrack.id);
              return;
          }

          if (String($currentTrack?.id) === String(prevTrack.id) && audioElement) {
              audioElement.currentTime = 0;
              audioElement.play().catch(() => {});
          }
          currentTrack.set(prevTrack);
      }
      if ($syncMode !== 'off') {
        pushJamState();
      }
  }

  /**
   * Handles the 'ended' event of the audio element.
   * Triggers scrobbling and plays the next track or repeats.
   */
  function handleEnded() {
      // A bulletin that runs out is the cue to resume, not to skip a track.
      if (newsSnapshot) {
          stopNews();
          return;
      }
      // Sent even when the halfway submission already fired: it carries the same timestamp, so it
      // corrects that listen's playing time to the whole track rather than adding a second listen.
      // A long set otherwise reports only the four minutes at which the first submission fired.
      scrobble(true);
      hasScrobbledFinished = true;
      if ($playerState.repeat === 'one') {
          audioElement.currentTime = 0;
          audioElement.play();
      } else {
          playNext();
      }
  }

  /**
   * Toggles the mute state and manages volume transitions.
   */
  function toggleMute() {
    muted = !muted;
    if (muted) {
      lastVolume = $playerState.volume;
      audioElement.volume = 0;
    } else {
      audioElement.volume = lastVolume / 100;
    }
  }

  /**
   * Handles time updates from the audio element.
   * Updates global player state, saves progress periodically, and handles mid-track scrobbling.
   */
  function handleTimeUpdate() {
    if (!audioElement) return;
    playerState.update(s => ({ ...s, progress: audioElement.currentTime }));
    updatePositionState();

    const length = currentLength();
    if (!hasScrobbledFinished && track && length > 0) {
        const threshold = Math.min(240, length / 2);
        if (audioElement.currentTime > threshold) {
            scrobble(true);
            hasScrobbledFinished = true;
        }
    }
  }

  /**
   * The length of whatever the element is playing, in seconds.
   *
   * Falling back to the track metadata is only right while the element plays
   * our own track: radio and a news bulletin put something else on it entirely,
   * and their length has nothing to do with the track that stays selected
   * underneath them.
   *
   * @returns {number} A usable length, or 0 when nothing knows one.
   */
  function currentLength() {
    const own = !newsSnapshot && !$radioChannel;
    return resolveDuration(audioElement?.duration, own ? track?.duration : 0);
  }

  /**
   * Polls the audio element while it plays.
   *
   * The `timeupdate` event is the obvious source for the position, and on a
   * desktop browser it is enough. The LG TV browser only fires it on a state
   * change -- play, pause, seek, ended -- and never on the ~4Hz cadence the
   * spec asks for, so the bar there sits still until someone touches the
   * transport. Reading `currentTime` on a timer of our own is the same number
   * from the same element and costs nothing, so it drives the bar everywhere
   * rather than only on the devices that misbehave.
   */
  function startProgressTicker() {
    stopProgressTicker();
    progressTicker = setInterval(() => {
      if (audioElement && !audioElement.paused) handleTimeUpdate();
    }, 250);
  }

  function stopProgressTicker() {
    if (progressTicker) {
      clearInterval(progressTicker);
      progressTicker = null;
    }
  }

  /**
   * Handles the 'loadedmetadata' event.
   * Sets track duration and restores saved progress if available.
   */
  function handleLoadedMetadata() {
    playerState.update(s => ({ ...s, duration: currentLength() }));
    updatePositionState();
    if (!initialized && track) {
        audioElement.currentTime = $playerState.progress || 0;
        initialized = true;
    }
  }

  /**
   * Handles the 'play' event.
   * Updates playing state and triggers initial scrobble.
   */
  function handlePlay() {
    // A context the browser suspended passes no sound at all, and play is the
    // moment that matters.
    equalizer.resume();
    playerState.update(s => ({ ...s, playing: true }));
    startProgressTicker();
    if (!hasScrobbledStarted) {
        listenStartedAtMs = Date.now();
        scrobble(false);
        hasScrobbledStarted = true;
    }
  }

  /**
   * The stream itself failed -- a missing file, a transcode that died, an
   * expired session. The audio element reports this on its own, without any
   * of the fetch calls in this component failing.
   */
  function handleAudioError() {
    if (!track) return;
    notify.error($t('notify.streamFailed', { title: track.title }));
  }

  /**
   * Handles the 'pause' event.
   * Updates playing state.
   */
  function handlePause() {
    playerState.update(s => ({ ...s, playing: false }));
    // The element fires its own `timeupdate` on a pause -- on every browser,
    // the TV included -- so the final position lands without a tick.
    stopProgressTicker();
  }

  /**
   * Handles the 'volumechange' event.
   * Updates global player volume state.
   */
  function handleVolumeChange() {
    playerState.update(s => ({ ...s, volume: audioElement.volume * 100 }));
  }

  /**
   * Seeks to a specific position in the track based on a click event on the progress bar.
   *
   * @param {MouseEvent} e - The click event.
   */
  function seek(e) {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const percentage = x / rect.width;
    // Not `audioElement.duration`: a chunked stream leaves that at `Infinity`,
    // and seeking to `Infinity * 0.5` throws the position away.
    if (duration <= 0) return;
    audioElement.currentTime = percentage * duration;
    if ($syncMode !== 'off') {
      pushJamState();
    }
  }

  /**
   * Changes the volume based on a click event on the volume bar.
   *
   * @param {MouseEvent} e - The click event.
   */
  function changeVolume(e) {
      const rect = e.currentTarget.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const vol = Math.max(0, Math.min(1, x / rect.width));
      audioElement.volume = vol;
      muted = (vol === 0);
  }

  /**
   * Formats an ISO date string (YYYY-MM-DD) into DD-MM-YYYY.
   *
   * @param {string} dateStr - The date string from the backend.
   * @returns {string|null} Formatted date or null if invalid.
   */
  function formatShortDate(dateStr) {
    if (!dateStr) return null;
    const parts = dateStr.split('T')[0].split('-');
    if (parts.length === 3) {
      // YYYY-MM-DD -> DD-MM-YYYY
      return `${parts[2]}-${parts[1]}-${parts[0]}`;
    }
    return null;
  }

  /**
   * Formats seconds into a "M:SS" string.
   *
   * @param {number} seconds - Time in seconds.
   * @returns {string} Formatted time string.
   */
  function formatTime(seconds) {
    // `Infinity` as well as `NaN`: an endless stream reports one, and it would
    // render as "Infinity:NaN".
    if (!Number.isFinite(seconds)) return "0:00";
    const min = Math.floor(seconds / 60);
    const sec = Math.floor(seconds % 60);
    return `${min}:${sec < 10 ? '0' : ''}${sec}`;
  }

  /**
   * Updates the Media Session API position state for OS integration.
   */
  function updatePositionState() {
    const length = currentLength();
    if ('mediaSession' in navigator &&
        'setPositionState' in navigator.mediaSession &&
        audioElement &&
        length > 0) {
      try {
        navigator.mediaSession.setPositionState({
          duration: length,
          playbackRate: audioElement.playbackRate || 1,
          position: Math.max(0, Math.min(audioElement.currentTime || 0, length))
        });
      } catch (e) {
        console.error("Failed to set position state", e);
      }
    }
  }

  /**
   * Cycles through repeat modes: none -> all -> one -> none.
   */
  function toggleRepeat() {
      playerState.update(s => {
          let next;
          if (s.repeat === 'none') next = 'all';
          else if (s.repeat === 'all') next = 'one';
          else next = 'none';
          return { ...s, repeat: next };
      });
  }

  /**
   * Toggles the shuffle mode.
   */
  function toggleShuffleMode() {
      playerState.update(s => ({ ...s, shuffle: !s.shuffle }));
      // A fresh run of shuffle starts its trail here, so the first "previous"
      // after switching it on goes back to the track that was playing.
      shuffleTrail = startTrail($currentTrack?.id);
  }

  /**
   * Toggles the sync mode: off -> host -> follower-jam -> follower-radio -> off.
   */
  function toggleJamMode() {
      syncMode.update(m => {
          if (m === 'off') return 'host';
          if (m === 'host') return 'follower-jam';
          if (m === 'follower-jam') return 'follower-radio';
          return 'off';
      });
  }

  /**
   * Increases the volume by 5%.
   */
  function volumeUp() {
    if (audioElement) {
      audioElement.volume = Math.min(1, audioElement.volume + 0.05);
      muted = false;
    }
  }

  /**
   * Decreases the volume by 5%.
   */
  function volumeDown() {
    if (audioElement) {
      audioElement.volume = Math.max(0, audioElement.volume - 0.05);
      if (audioElement.volume === 0) muted = true;
    }
  }

  /**
   * Toggles full-screen mode for the application.
   */
  function toggleFullScreen() {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(e => console.error("Fullscreen failed", e));
    } else if (document.exitFullscreen) {
      document.exitFullscreen();
    }
  }

  /**
   * Navigates to the album of the current track and highlights it.
   */
  function goToAlbum() {
    if (track && track.albumId) {
      highlightedTrackId.set(track.id);
      onnavigate(`album:${track.albumId}`);
    }
  }

  const track = $derived($radioChannel && $radioNowPlaying
    ? {
        id: $radioNowPlaying.track_id,
        title: $radioNowPlaying.title,
        artist: $radioNowPlaying.artist,
        album: $radioNowPlaying.album,
        coverArt: $radioNowPlaying.cover_art,
      }
    : $currentTrack);
  // The rating we last set ourselves, with the track it belongs to. `track` is
  // either the plain object in the `currentTrack` store or, on radio, one built
  // fresh from the timeline entry, so writing to `track.userRating` alone
  // repaints nothing and is lost on the next rebuild.
  let ownRating = $state(null);
  const currentRating = $derived(
    ownRating && ownRating.trackId === track?.id ? ownRating.rating : (track?.userRating || 0)
  );

  const primaryArtist = $derived.by(() => {
    if (track?.artists && track.artists.length > 0) return track.artists[0];
    if (track?.artist) {
      const firstName = track.artist.split(', ')[0];
      return firstName ? { name: firstName, id: track.artistId } : null;
    }
    return null;
  });
  const playing = $derived($playerState.playing);
  const progress = $derived(track ? $playerState.progress : 0);
  // Radio and a news bulletin are not the selected track, so they get no
  // fallback length; see currentLength().
  const fallbackLength = $derived((newsSnapshot || $radioChannel) ? 0 : (track?.duration ?? 0));
  const duration = $derived(track ? resolveDuration($playerState.duration, fallbackLength) : 0);
  const volume = $derived($playerState.volume);
  const repeatMode = $derived($playerState.repeat);
  const shuffleMode = $derived($playerState.shuffle);
  const syncColor = $derived(
    $syncMode === 'host' ? '#1db954' : 
    ($syncMode === 'follower-jam' ? '#3d91ff' : 
    ($syncMode === 'follower-radio' ? '#b266ff' : '#b3b3b3'))
  );
  const syncTitle = $derived(
    $syncMode === 'host' ? $t('player.syncHost') :
    ($syncMode === 'follower-jam' ? $t('player.syncRemote') :
    ($syncMode === 'follower-radio' ? $t('player.syncListener') : $t('player.syncOff')))
  );
  const isRadioActive = $derived($radioChannel !== null);
  const radioColor = $derived($radioChannel ? '#b266ff' : '#b3b3b3');
  const newsColor = $derived(newsSnapshot ? '#b266ff' : '#b3b3b3');
  // Radio listeners cannot steer the stream, exactly like a follower-radio client.
  const transportLocked = $derived($syncMode === 'follower-radio' || isRadioActive);
  const releaseDate = $derived(track ? (formatShortDate(track.date) || track.year || '') : '');
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

  $effect(() => {
    let interval;
    if ($syncMode !== 'off') {
        interval = setInterval(syncJam, 4000);
        syncJam();
    }
    return () => {
        if (interval) clearInterval(interval);
    };
  });

  $effect(() => {
    // Explicitly depend on state that should trigger a sync
    const _p = $playlist;
    const _t = track;
    const _pl = playing;

    if (shouldPushJamState($syncMode, isSyncing, $credentials.username)) {
        pushJamState();
    }
  });

  let lastTrackId = null;
  let hasScrobbledStarted = false;
  let hasScrobbledFinished = false;
  let initialized = false;

  /**
   * When this play of the current track began, in milliseconds.
   *
   * Sent with every submission for the track, so the server keys them all to the same listen. The
   * first submission fires halfway through and reports the seconds played so far; a later one --
   * when the track ends -- reports the real total and updates that same listen rather than adding a
   * second one. Without a client-set timestamp the server would stamp each submission with its own
   * clock and record two listens.
   */
  let listenStartedAtMs = null;

  /**
   * Sends a scrobble request to the server.
   *
   * @param {boolean} [submission=true] - Whether this is a final submission or just a "now playing" notification.
   */
  async function scrobble(submission = true) {
    if (!track || !$credentials.username) return;
    const params = $authParams;
    // How long this track actually played, and where. Both are MuMa's own parameters rather than
    // Subsonic ones; a listen without them records only that something was played, which cannot be
    // turned into listening time for a collection whose average track is a quarter of an hour.
    // Only a submission has a playing time to report -- a "now playing" ping fires at the start.
    const playedSeconds = submission && audioElement ? Math.floor(audioElement.currentTime) : null;
    let extra = playedSeconds ? `&playedSeconds=${playedSeconds}` : '';
    if (submission && listenStartedAtMs) extra += `&time=${listenStartedAtMs}`;
    const url = `${$credentials.url}/rest/scrobble?id=${track.id}&submission=${submission}&source=frontend${extra}&${params}`;
    try {
      const failure = await subsonicError(await fetch(url));
      if (failure) {
        // A lost scrobble does not interrupt playback, so it is a warning
        // rather than an error -- but it is silent otherwise, and a listening
        // history with holes in it is what people notice weeks later.
        notify.warning($t('notify.scrobbleFailed'), { detail: failure.message });
      }
    } catch (e) {
      console.error("Scrobble failed", e);
      notify.warning($t('notify.scrobbleFailed'), { detail: e.message });
    }
  }

  /**
   * Updates the rating of the current track.
   *
   * @param {number} rating - The new rating (1-5).
   */
  async function updateRating(rating) {
    if (!track) return;
    const trackId = track.id;
    const oldRating = currentRating;
    const newRating = oldRating === rating ? 0 : rating;

    // Optimistic update
    ownRating = { trackId, rating: newRating };
    track.userRating = newRating;

    try {
      // Subsonic reports its own errors (a throttled login, an id it cannot
      // parse, a failed write) in the body with HTTP 200, so the status in
      // the body is the only thing that says whether the rating was stored.
      // `subsonicError` is that check, shared with the track list.
      const failure = await subsonicError(
        await fetch(`${$credentials.url}/rest/setRating?id=${trackId}&rating=${newRating}&${$authParams}`)
      );
      if (failure) throw new Error(failure.message);
    } catch (e) {
      console.error("Failed to update rating:", e);
      ownRating = { trackId, rating: oldRating };
      track.userRating = oldRating;
      notify.error($t('notify.ratingFailed'), { detail: e.message });
    }
  }

  $effect(() => {
    if (track && track.id !== lastTrackId) {
        const isInitialLoad = !lastTrackId && !initialized;
        lastTrackId = track.id;
        hasScrobbledStarted = false;
        hasScrobbledFinished = false;
        
        // Don't load audio in remote-only jam mode
        if ($syncMode === 'follower-jam') return;
        // Radio owns the audio element while it is on; the controller decides
        // what to load and at which offset.
        if ($radioChannel) return;
        // A bulletin owns it too, and hands it back itself when it ends.
        if (newsSnapshot) return;

        if (audioElement) {
            audioElement.src = streamUrl;
            if (!isInitialLoad) {
                audioElement.play().catch(e => {
                    // An AbortError is the previous track's play() being
                    // cancelled by this one, which is what skipping does --
                    // not something to report.
                    if (e.name !== 'AbortError') {
                        console.error("Auto-play failed", e);
                        notify.error($t('notify.playbackFailed'), { detail: e.message });
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

    const handleGlobalKeyDown = (e) => {
      // Ignore if typing in an input field
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) {
        return;
      }

      switch (e.key) {
        case '5':
        case 'MediaPlayPause':
          togglePlay();
          break;
        case '4':
        case 'MediaTrackPrevious':
          playPrev();
          break;
        case '6':
        case 'MediaTrackNext':
          playNext();
          break;
        case '2':
        case 'VolumeUp':
          volumeUp();
          break;
        case '8':
        case 'VolumeDown':
          volumeDown();
          break;
        case '0':
        case 'VolumeMute':
          toggleMute();
          break;
        case ' ':
          e.preventDefault();
          togglePlay();
          break;
        case 'f':
        case 'F':
          toggleFullScreen();
          break;
        case 'Escape':
        case 'Backspace':
          if (window.history.length > 1) {
            window.history.back();
          }
          break;
        case 'Red':
        case 'ColorF0Red':
          activeView.set('home');
          break;
        case 'Green':
        case 'ColorF1Green':
          activeView.set('songs');
          break;
        case 'Yellow':
        case 'ColorF2Yellow':
          activeView.set('sets');
          break;
        case 'Blue':
        case 'ColorF3Blue':
          activeView.set('settings');
          break;
      }
    };

    const handleGlobalWheel = (e) => {
      // MX Master 3 thumb wheel sends deltaX. 
      // We use a threshold to avoid accidental triggers.
      if (Math.abs(e.deltaX) > 20) {
        if (e.deltaX > 0) volumeDown();
        else volumeUp();
      }
    };

    window.addEventListener('wheel', handleGlobalWheel, { passive: true });
    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => {
      window.removeEventListener('keydown', handleGlobalKeyDown);
      window.removeEventListener('wheel', handleGlobalWheel);
      if (radioTickInterval) clearInterval(radioTickInterval);
      if (radioRefreshInterval) clearInterval(radioRefreshInterval);
      if (radioClockInterval) clearInterval(radioClockInterval);
      stopProgressTicker();
    };
  });
</script>

<audio
  bind:this={audioElement}
  crossorigin="anonymous"
  ontimeupdate={handleTimeUpdate}
  onloadedmetadata={handleLoadedMetadata}
  onplay={handlePlay}
  onpause={handlePause}
  onvolumechange={handleVolumeChange}
  onended={handleEnded}
  onerror={handleAudioError}
></audio>

<footer class="flex items-center h-full px-2 md:px-4 relative">
  {#if $isMobile}
    <!-- Mobile Mini Player -->
    <div class="flex flex-1 items-center gap-3 min-w-0 py-2 h-full">
      {#if track}
        <img src={coverUrl} alt={track.title} class="w-11 h-11 rounded shadow-lg" onerror={(e) => e.target.src = '/images/spotify-fallback.svg'} />
        <div class="flex-1 min-w-0 cursor-pointer" onclick={goToAlbum} role="button" tabindex="0" onkeydown={(e) => e.key === 'Enter' && goToAlbum()}>
          <div class="text-[13px] font-bold text-white truncate">{track.title}</div>
          <div class="flex items-center gap-1.5 min-w-0">
            {#if primaryArtist}
              <img
                src={getArtistImageUrl(primaryArtist, $authParams)}
                alt={primaryArtist.name}
                class="w-4 h-4 rounded-full object-cover flex-shrink-0"
                onerror={(e) => e.target.src = '/images/unknown-artist.svg'}
              />
            {/if}
            <div class="text-[11px] text-[#b3b3b3] truncate">{track.artist}</div>
          </div>
        </div>
        <div class="flex items-center gap-0.5 flex-shrink-0">
          {#each [1, 2, 3, 4, 5] as star (star)}
            <button
              aria-label="{star} sterren"
              class="bg-transparent border-none p-0 cursor-pointer transition-colors { currentRating >= star ? 'text-brand' : 'text-white/10' }"
              onclick={() => updateRating(star)}
            >
              <svg viewBox="0 0 24 24" width="11" height="11" fill="currentColor">
                <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"></path>
              </svg>
            </button>
          {/each}
        </div>
      {:else}
        <div class="flex-1 flex items-center gap-3 min-w-0">
          <div class="w-11 h-11 bg-white/5 rounded flex items-center justify-center">
            <svg viewBox="0 0 24 24" width="24" height="24" fill="#535353">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 14.5c-2.49 0-4.5-2.01-4.5-4.5S9.51 7.5 12 7.5s4.5 2.01 4.5 4.5-2.01 4.5-4.5 4.5zm0-7c-1.38 0-2.5 1.12-2.5 2.5s1.12 2.5 2.5 2.5 2.5-1.12 2.5-2.5-1.12-2.5-2.5-2.5z"></path>
            </svg>
          </div>
          <div class="text-[13px] text-[#b3b3b3] italic font-medium">{$t('player.nothingPlaying')}</div>
        </div>
      {/if}
      <div class="flex items-center gap-3 px-2">
        {#if equalizerSupported}
          <button
            bind:this={equalizerButtonEl}
            class="bg-transparent border-none p-0 cursor-pointer transition-colors {$equalizerSettings.enabled ? 'text-brand' : 'text-[#b3b3b3]'}"
            onclick={() => (showEqualizer = !showEqualizer)}
            aria-label={$t('equalizer.title')}
            aria-pressed={showEqualizer}
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
              <path d="M4 20V14M4 10V4M12 20V12M12 8V4M20 20V16M20 12V4M1 14h6M9 8h6M17 16h6"></path>
            </svg>
          </button>
        {/if}
        <button
          class="bg-transparent border-none p-0 text-white hover:scale-105 transition-transform {transportLocked ? 'opacity-50 cursor-not-allowed' : ''}"
          onclick={togglePlay} 
          disabled={transportLocked}
          aria-label={playing ? "Pauze" : "Afspelen"}
        >
          {#if playing}
            <svg viewBox="0 0 24 24" width="32" height="32" fill="currentColor">
              <path d="M5.7 3a.7.7 0 0 0-.7.7v16.6a.7.7 0 0 0 .7.7h2.6a.7.7 0 0 0 .7-.7V3.7a.7.7 0 0 0-.7-.7H5.7zm10 0a.7.7 0 0 0-.7.7v16.6a.7.7 0 0 0 .7.7h2.6a.7.7 0 0 0 .7-.7V3.7a.7.7 0 0 0-.7-.7h-2.6z"></path>
            </svg>
          {:else}
            <svg viewBox="0 0 24 24" width="32" height="32" fill="currentColor">
              <path d="M7.05 3.606l13.49 7.788a.7.7 0 0 1 0 1.212L7.05 20.394A.7.7 0 0 1 6 19.788V4.212a.7.7 0 0 1 1.05-.606z"></path>
            </svg>
          {/if}
        </button>
        {#if track}
          <button 
            class="bg-transparent border-none p-0 text-[#b3b3b3] hover:text-white transition-colors {transportLocked ? 'opacity-50 cursor-not-allowed' : ''}" 
            onclick={playNext} 
            disabled={transportLocked}
            aria-label={$t('player.next')}
          >
            <svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor">
              <path d="M16.7 3.3a.7.7 0 0 0-.7.7v6.85L6.05 4.806A.7.7 0 0 0 5 5.412v13.175a.7.7 0 0 0 1.05.607L16 13.15v6.85a.7.7 0 0 0 .7.7h1.6a.7.7 0 0 0 .7-.7V4a.7.7 0 0 0-.7-.7h-1.6z"></path>
            </svg>
          </button>
        {/if}
      </div>
    </div>
    <!-- Progress bar for mobile -->
    {#if track}
      <div class="absolute top-0 left-0 w-full h-[2px] bg-white/10">
        <div class="h-full bg-white transition-[width] duration-100" style="width: {progressPercent(progress, duration)}%"></div>
      </div>
    {/if}
    {#if showEqualizer}
      <div bind:this={equalizerPanelEl} class="fixed inset-x-0 bottom-0 z-50 flex justify-center p-3 pb-24">
        <Equalizer onclose={() => (showEqualizer = false)} />
      </div>
    {/if}
  {:else}
    <!-- Desktop Player -->
    <div class="w-[30%] hidden md:flex items-center gap-3">
      {#if track}
        <img src={coverUrl} alt={track.title} class="w-14 h-14 rounded" onerror={(e) => e.target.src = '/images/spotify-fallback.svg'} />
        <div class="track-info min-w-0">
          <div
            role="button"
            tabindex="0"
            class="text-sm font-medium truncate hover:underline cursor-pointer"
            onclick={goToAlbum}
            onkeydown={(e) => e.key === 'Enter' && goToAlbum()}
          >{track.title}</div>
          <div class="flex items-center gap-1.5 min-w-0">
            {#if primaryArtist}
              <img
                src={getArtistImageUrl(primaryArtist, $authParams)}
                alt={primaryArtist.name}
                class="w-5 h-5 rounded-full object-cover flex-shrink-0"
                onerror={(e) => e.target.src = '/images/unknown-artist.svg'}
              />
            {/if}
            <ArtistList
              artist={track.artist}
              artistId={track.artistId}
              artists={track.artists}
              onnavigate={onnavigate}
            />
          </div>
        </div>
      {/if}
    </div>

    <div class="flex-1 md:w-[40%] max-w-[600px] flex flex-col items-center gap-2">
      <div class="flex items-center gap-4 md:gap-6">
        <button class="hidden md:flex flex-col items-center bg-transparent border-none p-0 cursor-pointer transition-colors hover:text-white {shuffleMode ? 'text-brand' : 'text-[#b3b3b3]'}" onclick={toggleShuffleMode} aria-label={$t('queue.shuffle')}>
          <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
            <path d="M13.151.922a.75.75 0 1 0-1.06 1.06L13.109 3H10.3a5 5 0 0 0-4.054 2.115L2.615 10H1.25a.75.75 0 0 0 0 1.5h2.185a5 5 0 0 0 4.054-2.115L11.121 5H13.11l-1.019 1.017a.75.75 0 1 0 1.06 1.06L15.424 4.8a.75.75 0 0 0 0-1.06L13.15 1.472a.75.75 0 0 0-.001-.55zM13.151 9.922a.75.75 0 1 0-1.06 1.06L13.109 12H11.12l-1.144-1.636a.75.75 0 1 0-1.232.862l1.378 1.968A5 5 0 0 0 14.176 13.5h.194l-1.269 1.271a.75.75 0 1 0 1.06 1.06L16.43 13.56a.75.75 0 0 0 0-1.06l-2.274-2.273a.75.75 0 0 0-1.005-.305zM5.185 3.5h1.077L7.406 5.137a.75.75 0 0 0 1.232-.863l-1.378-1.967A5 5 0 0 0 3.235 1.5H1.25a.75.75 0 0 0 0 1.5h2.185a3.5 3.5 0 0 1 2.838 1.48L5.185 3.5z"></path>
          </svg>
          {#if shuffleMode}
            <div class="w-1 h-1 bg-brand rounded-full mt-0.5"></div>
          {/if}
        </button>
        <button 
          class="bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors hover:text-white text-[#b3b3b3] {transportLocked ? 'opacity-50 cursor-not-allowed' : ''}" 
          onclick={playPrev} 
          disabled={transportLocked}
          aria-label={$t('player.previous')}
        >
          <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
            <path d="M3.3 1a.7.7 0 0 1 .7.7v5.15l9.95-5.744a.7.7 0 0 1 1.05.606v12.575a.7.7 0 0 1-1.05.607L4 9.15v5.15a.7.7 0 0 1-.7.7H1.7a.7.7 0 0 1-.7-.7V1.7a.7.7 0 0 1 .7-.7h1.6z"></path>
          </svg>
        </button>
        <button 
          class="w-9 h-9 bg-white rounded-full text-black flex items-center justify-center cursor-pointer transition-transform hover:scale-105 {transportLocked ? 'opacity-50 cursor-not-allowed' : ''}" 
          onclick={togglePlay}
          disabled={transportLocked}
        >
          {#if playing}
            <svg viewBox="0 0 16 16" width="16" height="16" fill="black">
              <path d="M2.7 1a.7.7 0 0 0-.7.7v12.6a.7.7 0 0 0 .7.7h2.6a.7.7 0 0 0 .7-.7V1.7a.7.7 0 0 0-.7-.7H2.7zm7.43 0a.7.7 0 0 0-.7.7v12.6a.7.7 0 0 0 .7.7h2.6a.7.7 0 0 0 .7-.7V1.7a.7.7 0 0 0-.7-.7h-2.6z"></path>
            </svg>
          {:else}
            <svg viewBox="0 0 16 16" width="16" height="16" fill="black">
              <path d="M3 1.713a.7.7 0 0 1 1.05-.607l10.89 6.288a.7.7 0 0 1 0 1.212L4.05 14.894A.7.7 0 0 1 3 14.288V1.713z"></path>
            </svg>
          {/if}
        </button>
        <button 
          class="bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors hover:text-white text-[#b3b3b3] {transportLocked ? 'opacity-50 cursor-not-allowed' : ''}" 
          onclick={playNext} 
          disabled={transportLocked}
          aria-label={$t('player.next')}
        >
          <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
            <path d="M12.7 1a.7.7 0 0 0-.7.7v5.15L2.05 1.106A.7.7 0 0 0 1 1.712v12.575a.7.7 0 0 0 1.05.607L12 9.15v5.15a.7.7 0 0 0 .7.7h1.6a.7.7 0 0 0 .7-.7V1.7a.7.7 0 0 0-.7-.7h-1.6z"></path>
          </svg>
        </button>
        <button class="hidden md:flex flex-col items-center relative bg-transparent border-none p-0 cursor-pointer transition-colors hover:text-white {repeatMode !== 'none' ? 'text-brand' : 'text-[#b3b3b3]'}" onclick={toggleRepeat} aria-label={$t('player.repeat')}>
          <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
            <path d="M0 4.75A3.75 3.75 0 0 1 3.75 1h8.5A3.75 3.75 0 0 1 16 4.75v5a3.75 3.75 0 0 1-3.75 3.75H9.81l1.018 1.018a.75.75 0 1 1-1.06 1.06L6.939 12.75l2.829-2.828a.75.75 0 1 1 1.06 1.06L9.811 12h2.439a2.25 2.25 0 0 0 2.25-2.25v-5a2.25 2.25 0 0 0-2.25-2.25h-8.5A2.25 2.25 0 0 0 1.5 4.75v5A2.25 2.25 0 0 0 3.75 12H5v1.5H3.75A3.75 3.75 0 0 1 0 9.75v-5z"></path>
          </svg>
          {#if repeatMode === 'one'}
            <span class="absolute text-[7px] font-bold top-1/2 left-1/2 -translate-x-1/2 -translate-y-[60%] text-brand">1</span>
          {/if}
          {#if repeatMode !== 'none'}
            <div class="w-1 h-1 bg-brand rounded-full mt-0.5"></div>
          {/if}
        </button>
      </div>
      <div class="hidden md:flex w-full items-center gap-2 text-[11px] text-[#b3b3b3]">
        <span>{formatTime(progress)}</span>
      <div 
        role="button"
        tabindex="0"
        class="flex-1 h-1 bg-[#4d4d4d] rounded-sm cursor-pointer {transportLocked ? 'pointer-events-none opacity-50' : ''}"
        onclick={seek}
        onkeydown={(e) => e.key === 'Enter' && seek(e)}
        aria-label={$t('player.seek')}
      >
          <div class="h-full bg-white rounded-sm" style="width: {progressPercent(progress, duration)}%"></div>
      </div>
        <span>{formatTime(duration)}</span>
      </div>
    </div>

    <div class="w-[30%] hidden md:flex justify-end items-center gap-3">
      {#if track}
        <div class="flex gap-0.5 mr-2">
          {#each [1, 2, 3, 4, 5] as star (star)}
            <button
              aria-label="{star} sterren"
              class="bg-transparent border-none p-0.5 cursor-pointer transition-colors { currentRating >= star ? 'text-brand' : 'text-white/10 hover:text-white/30' }"
              onclick={() => updateRating(star)}
            >
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"></path>
              </svg>
            </button>
          {/each}
        </div>
      {/if}
      <div class="relative flex items-center">
        <button
          class="bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors hover:text-white"
          style="color: {radioColor}"
          onclick={toggleRadio}
          title={isRadioActive ? 'Radio: aan het luisteren' : 'Radio (beta)'}
          aria-label={$t('player.radio')}
          aria-pressed={isRadioActive}
          aria-expanded={showRadioPicker}
        >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">
              <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 4a6 6 0 1 1 0 12 6 6 0 0 1 0-12zm0 4a2 2 0 1 0 0 4 2 2 0 0 0 0-4z" />
            </svg>
        </button>
        {#if showRadioPicker}
          <div
            class="absolute bottom-full right-0 mb-3 w-56 bg-[#282828] rounded-md shadow-xl border border-white/5 py-1 z-50"
            role="menu"
          >
            <div class="px-3 py-2 text-[10px] uppercase tracking-wider text-[#b3b3b3]">
              {$t('radio.chooseChannel')}
            </div>
            {#each radioChannels as channel (channel.slug)}
              <button
                class="w-full text-left px-3 py-2 bg-transparent border-none cursor-pointer text-sm text-white hover:bg-white/10 transition-colors"
                role="menuitem"
                onclick={() => startRadio(channel)}
              >
                <span class="font-bold">{channel.name}</span>
                <span class="block text-[11px] text-[#b3b3b3]">
                  {describeFilter(channel.filter, $t('management.radio.wholeLibrary'))}
                </span>
              </button>
            {/each}
          </div>
        {/if}
      </div>
      <button
        class="bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors hover:text-white"
        style="color: {newsColor}"
        onclick={toggleNews}
        title={newsSnapshot ? $t('news.playing') : $t('news.play')}
        aria-label={$t('news.play')}
        aria-pressed={newsSnapshot !== null}
      >
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">
          <path d="M20 3H4a2 2 0 0 0-2 2v12a3 3 0 0 0 3 3h14a3 3 0 0 0 3-3V5a2 2 0 0 0-2-2zM5 18a1 1 0 0 1-1-1V5h12v12a3 3 0 0 0 .17 1zm14 0a1 1 0 0 1-1-1V5h2v12a1 1 0 0 1-1 1zM6 7h8v2H6zm0 4h8v2H6zm0 4h5v2H6z" />
        </svg>
      </button>
      <button
        class="bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors"
        onclick={toggleJamMode}
        title={syncTitle}
        style="color: {syncColor}"
      >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-5.5-8c0 3.03 2.47 5.5 5.5 5.5s5.5-2.47 5.5-5.5-2.47-5.5-5.5-5.5-5.5 2.47-5.5 5.5z"></path>
          </svg>
      </button>
      {#if equalizerSupported}
        <div class="relative">
          <button
            bind:this={equalizerButtonEl}
            class="bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors hover:text-white {$equalizerSettings.enabled ? 'text-brand' : 'text-[#b3b3b3]'}"
            onclick={() => (showEqualizer = !showEqualizer)}
            aria-label={$t('equalizer.title')}
            aria-pressed={showEqualizer}
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
              <path d="M4 20V14M4 10V4M12 20V12M12 8V4M20 20V16M20 12V4M1 14h6M9 8h6M17 16h6"></path>
            </svg>
          </button>
          {#if showEqualizer}
            <div bind:this={equalizerPanelEl} class="absolute bottom-full right-0 mb-3 z-50">
              <Equalizer onclose={() => (showEqualizer = false)} />
            </div>
          {/if}
        </div>
      {/if}
      <button class="mr-2 bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors hover:text-white text-[#b3b3b3]" onclick={ontoggleQueue} aria-label={$t('queue.title')}>
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
        onwheel={(e) => {
          if (e.deltaY > 0) volumeDown();
          else volumeUp();
        }}
        onkeydown={(e) => e.key === 'Enter' && changeVolume(e)}
        aria-label={$t('player.volume')}
      >
        <div class="h-full bg-white rounded-sm" style="width: {volume}%"></div>
      </div>
    </div>
  {/if}

  {#if track && releaseDate}
    <div class="hidden md:block absolute bottom-1 right-4 text-[10px] text-white/30 pointer-events-none select-none">
      {releaseDate}
    </div>
  {/if}
</footer>

<style>
</style>
