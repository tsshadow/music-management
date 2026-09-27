- **The play button on a daily-mix card could not be seen on a phone or tablet** (issue #99).
  It only appeared on hover (`opacity-0 group-hover:opacity-100`), and a touchscreen has no hover.
  On a coarse pointer it is now always visible and 48px (the style guide's touch target); with a
  mouse it still appears on hover, and now also on keyboard focus.

<!-- release notes -->

- The play button on daily-mix cards is now visible on phones and tablets.
