- **Web: logging out marks the device as signed out.** The web UI's logout now waits at most five
  seconds for the Android shell's own sign-out and records a device-level `muma_signed_out` mark,
  so the shell's next boot shows the login page instead of signing back in from credentials the
  phone still holds; any successful sign-in lifts it. Inside the shell the login page offers a
  native "Sign in with Google" button (the Google Identity Services button stays browser-only), and
  a Google sign-in there hands the session to the phone like a password sign-in does. Browser
  behaviour is unchanged. Bug report 106.

<!-- release notes -->

- **Uitloggen in de app blijft uitgelogd.** Na uitloggen logt de app bij de volgende start niet meer
  vanzelf opnieuw in, en in de app kun je weer met Google inloggen. In de browser verandert niets.
