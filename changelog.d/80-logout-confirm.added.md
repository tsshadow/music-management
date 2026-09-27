- **Logging out asks first** (issue #80). The profile menu's "Log out" logged out on a single tap,
  stopping playback and emptying the queue, although the style guide's Session controls rule says a
  logout always confirms first. It now opens a "Log out?" dialog that says playback stops and the
  queue is cleared -- and, in the app, that downloads stay on the device. Cancel, Escape or a tap
  beside the dialog changes nothing; confirming runs the existing sign-out unchanged (bug report
  106), once, however often the button is tapped. The dialog reuses `Modal.svelte`, which gains a
  `widthClass` prop and dialog semantics; the style guide now describes the Confirmation dialog.

<!-- release notes -->

- Logging out now asks for confirmation first, so a stray tap no longer stops your music.
