# Station Start Flashes An Error And Pause Is Grey

# status: fixed

# reported problem
On 2026-11-07, with app 7.19.1, the stations played, but a message that the station does not work showed for a short time. The pause button of the player was also not available during a station.

# Possible reason
This comes from the code. No device log shows it. `startStation` sets `liveStation` in the web layer, and the service then gets `setMediaItems`. `onAddMediaItems` starts the station and returns an empty list, so the player goes to `STATE_ENDED` while the station list loads. The plugin sends `ended`, and `handleEnded` in `Player.svelte` showed `notify.streamFailed`. The errors of the native retry reached `handleAudioError` in the same way.

`transportLocked` included every kind of radio, and the play button used that lock.

# solution
On the native shell, `handleEnded` and `handleAudioError` do not notify for a station, because the service owns the retry. In the browser the message stays. The new lock `playLocked` applies only to a `follower-radio` jam, so a station can pause. A MuMa Radio channel has no pause, so the play button leaves the channel. `player.test.js` and `playerNativeMode.test.js` cover this. A check on a phone is in issue #214.
