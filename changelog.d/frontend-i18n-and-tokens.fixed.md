- **The web interface no longer mixes Dutch into English.** Error messages, confirmation dialogs,
  titles and the lock-screen fallback "Onbekend nummer" were typed into the components in Dutch and
  ignored the language setting; they now come from the locale files. Numbers and dates follow the
  chosen language instead of always being formatted Dutch (`1,234` in English, `1.234` in Dutch).
  A unit test fails if one of the moved phrases or a fixed `'nl-NL'` comes back (bug report 083).
- **Colour tokens instead of hex values in the web frontend.** Five greys the interface already
  used got a token (`muma-spotify-muted`, `-subtle`, `-raised`, `-hover`, `-highlight`) and about
  820 arbitrary colour classes were rewritten to tokens with the same value, so nothing changes on
  screen. The Save button on a genre page has a hover state again (`bg-opacity-*` compiles to
  nothing in Tailwind v4), and the search box no longer fetches the full genre and label lists
  again every time the layout switches between phone and desktop.

<!-- release notes -->

- **The web interface speaks one language.** Messages, dialogs and numbers that stayed Dutch after
  switching to English now follow your language setting.
