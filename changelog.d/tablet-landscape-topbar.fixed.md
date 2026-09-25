- **A tablet in landscape shows the search box and the profile button again.** The top bar chose
  between its phone and desktop version on `isMobile`, which is true on every touch screen, while
  the page layout switches at Tailwind's `md` breakpoint (768 px). From 768 px up a touch screen got
  the phone bar, which its own `md:hidden` then hid, and no desktop bar at all -- as did a desktop
  window between 768 and 1023 px. Present since 0.63.0, not caused by the colour-token rewrite in
  0.74.1; every token class was compiled and checked, and a test now keeps it that way. Bug report 090.
<!-- release notes -->
- On a tablet in landscape the search box and the profile button are back in the top bar.
