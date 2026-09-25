- **Google sign-in accepts only a verified e-mail address, and a taken username is a 409.** Bug
  report 079. A Google ID token whose `email_verified` claim is not true is refused with 401: the
  address is what an admin reads when approving a request and becomes the new account's username.
  A rejected token's 401 no longer repeats the Google library's reason. Approving a request whose
  e-mail address is already a username (in any case) answers 409 with a hint to link the request to
  that account, instead of a 500.
- **Logins through LMS are rate limited per client again, and a forged `X-Forwarded-For` no longer
  picks a bucket.** LMS now passes the client address it resolved to MuMa, both on its password check
  for every Subsonic request and on a proxied `/muma/api/auth/login`; it sent none, so every login
  on `lms.<domain>` counted as the LMS container. MuMa believes that header only from a trusted
  network (`AUTH_TRUSTED_PROXIES`, default loopback and the private ranges) or a caller with the
  system key, and reads it from the right instead of taking the client-written left-most entry. A
  login now counts per client and account (10 a minute) and per account from anywhere
  (`AUTH_RATE_LIMIT_ACCOUNT_ATTEMPTS`, 50 a minute), so one device with a stale password no longer
  locks the account for everyone.

<!-- release notes -->

- **Google sign-in** now requires a Google account with a verified e-mail address.
- **One device with an old password** no longer locks everyone else out of that account.
