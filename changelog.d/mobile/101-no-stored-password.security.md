- **The app no longer stores the password after signing in** (issue #101). Builds before it kept
  the password in the plain preferences (`staticPassword`) -- after a Google sign-in, the MuMa API
  key in its place -- for two jobs: re-logging in when MuMa refused the stored key, and, blank,
  meaning "signed out".
  - **Signed in.** An explicit flag replaces the blank password (`Settings.signedIn`, read through
    `ActiveServerProvider.isSignedIn`). The shell bridge hands the web the flag and the MuMa key
    instead of the password, and a sign-in on the web hands the phone the name, key and account
    id (`saveCredentials({username, mumaApiKey, mumaUserId})`) instead of the pair.
  - **After updating.** On first start, a stored name and password become "signed in" and the
    password is removed. The MuMa key, the Subsonic token and the queue stay, so nobody has to sign
    in again. The unused legacy server table has its password column blanked.
  - **A refused key.** MuMa answering 401 to the stored key now ends the session instead of
    logging in again with the password: the web shows its sign-in page (password or Google), and
    Android Auto answers "Sign in again in the MuMa app on your phone". The key is permanent, so
    a refusal means it was revoked or the account is gone. A key without an account id asks
    `GET /api/auth/verify` for it.
  - **Diagnostics.** The log redaction also masks a `password` query parameter, which a failed
    password change could quote into the web action trail.
<!-- release notes -->
- The app no longer stores your password. After updating you stay signed in. If your account's key
  is ever revoked, the app asks you to sign in again, and the car says to sign in on your phone.
