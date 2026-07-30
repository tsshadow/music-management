# title: Ultrasonic Google Sign-In selects an account but silently returns to the login dialog

# status: fixed

# reported problem
Even with bugs 011 and 012 fixed (Android OAuth client registered, `GetSignInWithGoogleOption`
in use, no `ping()` gate), the user still ends up back at the login dialog after picking an
account in the Google account picker: they click "Sign in with Google", the picker opens, they
select their account, and then they land back on the same login dialog requiring a manually
typed username and password — with no error message shown anywhere. This defeats the purpose of
Google Sign-In as a full alternative to manual login, matching the web frontend's behavior.

# Possible reason
Both `NavigationActivity.performWelcomeGoogleSignIn()` and
`EditServerFragment.handleGoogleSignInResult()` checked the credential returned by
`CredentialManager.getCredential()` with a naive `if (credential is GoogleIdTokenCredential)`.

Per Android's Credential Manager API, a third-party credential type (such as Google's) is never
delivered across the Credential Manager IPC boundary as its concrete subclass. It always arrives
as a generic `androidx.credentials.CustomCredential` (a `type` string plus a raw `data: Bundle`),
even though `GoogleIdTokenCredential` itself happens to extend `CustomCredential` in the
`googleid` library's own class hierarchy. The caller is required to check
`credential.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL` and then explicitly
parse it via `GoogleIdTokenCredential.createFrom(credential.data)` — this is Google's documented
pattern for Credential Manager + Sign in with Google.

Because the `is GoogleIdTokenCredential` cast always failed, both call sites hit a silent
`return` (or, in the welcome flow, `return@launch`) before the ID token was ever extracted and
before any network call to `/api/auth/google` was made — no exception, no log, no user-visible
error. The dialog was simply left exactly as it was, indistinguishable from having done nothing
at all. Bugs 009–011 never actually reached this line successfully on a real device before (each
was blocked earlier in the flow), so this bug was masked until bug 011's fix let
`getCredential()` itself start succeeding.

# solution
In both `NavigationActivity.performWelcomeGoogleSignIn()` and
`EditServerFragment.handleGoogleSignInResult()`, replaced the naive cast with the standard
pattern: check `credential is CustomCredential && credential.type ==
GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL`, then parse it with
`GoogleIdTokenCredential.createFrom(credential.data)` (wrapped in a try/catch for
`GoogleIdTokenParsingException`). Added an explicit, logged, user-visible error path
(`background_task_network_error`) for any unexpected credential type or parse failure, instead
of silently returning.
