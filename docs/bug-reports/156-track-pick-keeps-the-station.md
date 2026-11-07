# A Track Picked During A Station Does Not Play

# status: fixed

# reported problem
On 2026-11-07, with app 7.20.0, a station or MuMa Radio played. The user tapped a track in a list. The station kept playing, and the track did not start. The user expected the player to leave the radio and play the track.

# Possible reason
A tap sets `currentTrack`, and nothing else. While a station or a channel is on, `Player.svelte` ignores that store. In the browser, `track` is the station, and the load effect returns early for `liveStation` and `radioChannel`. On the native shell, the queue sync effect does nothing while radio is on. No code left the radio for a new track.

# solution
`Player.svelte` has an effect that sees a new `currentTrack` while a station or a channel is on. It calls `leaveRadioForTrack`, which ends the radio without a pause. In the browser the load effect then plays the track. On the native shell the service gets `stopRadio`, and the next queue sync has `autoplay`. The effect skips the writes that are not a pick: the app-start restore, a jam that this device follows, and the service that reports its own track. `player.test.js` and `playerNativeMode.test.js` cover a station and a channel.
