# Phone Now Playing Screen Has No News Button

# status: fixed

# reported problem
"Waar is de nieuwsknop?" (2026-09-24, looking at a screenshot of the app's full-screen player).
The phone's now-playing screen offers equalizer, radio, song versions and queue in its bottom row,
but no way to start the news of the hour. On the desktop web player the newspaper button sits
right next to the radio button in the player bar.

# Possible reason
`Player.svelte` renders two layouts. Its desktop branch has had the news button
(`onclick={toggleNews}`, tinted `#b266ff` via `newsColor` while `newsSnapshot` is set) since news of
the hour shipped. The phone branch shows a mini player and hands everything else to
`NowPlaying.svelte` (introduced 2026-09-12, b817298e3), passing the rating, transport, equalizer,
queue and -- since 0ba6774bf -- the radio. The news was never part of that hand-over:
`NowPlaying.svelte` had no news prop and no news button, so on a phone, and therefore in the
Capacitor app whose UI is this web frontend since the legacy Kotlin UI was removed, the only way to
the bulletin was the media notification or Android Auto.

Nothing caught it because the unit tests for the news toggle click the desktop bar's button
(`getAllByLabelText("Nieuws van het uur")[0]`), and the screenshot suite never opens the full-screen
player.

# solution
`NowPlaying.svelte` takes `newsActive` and `ontoggleNews` and renders the news button in its bottom
row directly after the radio button, with the radio button's pattern: grey `#B3B3B3`, `#b266ff`
while a bulletin plays, `aria-pressed`, `aria-label` `news.play`, `data-testid="now-playing-news"`,
and the desktop bar's newspaper glyph at 24px. `Player.svelte` wires it with
`newsActive={newsSnapshot !== null}` and `ontoggleNews={toggleNews}`, the same handler the desktop
button calls, so the native-shell path (`platform.player.toggleNews()`) and the browser path are
both covered without new logic.

Tests: `nowPlaying.test.js` (button only when wired, click calls the handler, `aria-pressed` and
tint follow `newsActive`) and `player.test.js` (on a phone, the full-screen player's news button
reaches `toggleNews` and reports a missing bulletin the same way the desktop button does).
