# Tablet in Landscape Shows No Search Box and No Profile Button

# status: fixed

# reported problem
Reported by Teun, 2026-09-25, on muma-mobile 7.4.7 (the web UI of server 0.74.1): on a tablet in
landscape the top bar is empty -- no search box and no profile-photo (account) button. Phones in
portrait and the desktop browser were not reported. 7.4.7 was the first app version with MR !982
(i18n, ~820 colour classes rewritten onto `muma-spotify-*` tokens, `searchFacets.js`) and MR !977,
so the token rewrite was the first suspect.

# Possible reason
Not a regression of !982 or !977. Reproduced with Playwright against the frontend of both
`release-v0.74.0` and `release-v0.74.1` with identical results: at 1280x800, 1194x834, 1180x820,
1024x768 and 900x700 with a touch screen (`hasTouch`, so `(pointer: coarse)` matches) the search
field and the profile button are absent; at 412x915 they are present; without touch they are present
from 1024 px up and absent at 900x700.

`App.svelte` sets `isMobile` to `innerWidth < 1024 || (pointer: coarse)`, so a tablet is "mobile" at
any width. `TopBar.svelte` forks on that store: `{#if $isMobile}` renders the phone's one-line bar,
`{:else}` the desktop bar. Each branch also carries a CSS backstop for Tailwind's `md` breakpoint
(48rem = 768 px): the phone bar has `md:hidden`, the desktop bar `hidden md:flex`. For a coarse
pointer at 768 px or wider the JavaScript picks the phone bar and the CSS then hides it, while the
desktop bar -- the one the CSS would show -- is never rendered. The rest of the shell (`App.svelte`'s
grid, sidebar, player bar) follows `md`, so the tablet gets the desktop layout with no top bar in it.
The same gap hits a desktop browser window between 768 and 1023 px wide.

The gate dates from `d0a0778af` ("move the phone's Songs/Sets toggle into the top bar", shipped in
0.63.0); before it a single bar served every width and only CSS decided what it showed.

The token rewrite was checked as well: every class in `src/` that uses a `@theme` colour token was
compiled with Tailwind's own compiler against `src/app.css`, and every one of them produces a rule. The browser
console shows no render error at the tablet viewports.

# solution
`store.js` gains `isWideLayout`, a readable store on `matchMedia('(min-width: 48rem)')` -- the same
breakpoint the `md:` classes use. `TopBar.svelte` renders the phone bar only when
`$isMobile && !$isWideLayout`; from `md` up it renders the desktop bar, whose search field and
profile button the CSS shows. The phone (below `md`) and the plain desktop are unchanged.

Tests:
- `tests/unit/topBar.test.js`, "TopBar on a tablet in landscape": with `isMobile` true and the `md`
  query matching, the search field and profile button are rendered with no `md:hidden` ancestor, and
  the desktop bar (not the phone bar) is the one used. Both fail against the old gate.
- `tests/browser/tablet.spec.js`: 1280x800 with `hasTouch` against the real stylesheet, asserting the
  search field and profile button are visible.
- `tests/unit/themeTokenClasses.test.js`: compiles `src/app.css` with Tailwind and fails on any
  theme-token colour class in `src/` that produces no rule, so a future token rewrite cannot
  silently drop a colour.
