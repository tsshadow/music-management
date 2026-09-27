- **The web player keeps no copy of the password after signing in** (issue #101). Since issue #72
  it signs nothing, but `lms_credentials` in localStorage still held it -- and, after a Google
  sign-in, the MuMa API key in its place -- for two jobs: re-logging in when MuMa refused the stored
  key (`Management.svelte`'s auto-login), and telling the Android shell's boot whether to sign in
  again.
  - **Sign-in.** `signIn` and the Google path store the name only; the login form clears its
    password field once the sign-in succeeds.
  - **Existing sessions.** A stored password is dropped the first time the page loads
    (`withoutPassword`, and the persisted value is rewritten without it) -- the session itself
    stays, it lives on as the MuMa key and the Subsonic token.
  - **A refused key.** MuMa answering 401/403 to the stored key at start-up or on the management
    screen now ends the session and shows the login page. It used to be traded silently for a new
    key with the stored password. The key is permanent, so a refusal means it was revoked or the
    account is gone.
  - **Signed in.** "Signed in" is one explicit state, `signedIn` (a name or a MuMa session), and
    no longer depends on a stored password.
  - **Also removed.** The unbuilt `spotify-ui` copy of the player in the LMS tree
    (`services/music-management-server/src/lms/ui/spotify-ui`, issue #102), which still signed
    with `p=<password>`. Nothing built, served or imported it: `Dockerfile-release` copies
    `services/frontend` into LMS's `docroot/spotify`, which `SpotifyResource` serves. Its accepted
    SAST finding is gone with it.
<!-- release notes -->
- The web player no longer remembers your password after you sign in. If your account's key is
  revoked, you now see the sign-in page instead of being signed in again in the background.
