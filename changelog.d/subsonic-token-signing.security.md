- **The password is no longer in every Subsonic URL.** The web player signed each stream, cover
  and API request as `u=<name>&p=<password>` -- the password in plain text, so in every access log,
  proxy log and browser history entry it passed. LMS accepts the salted `t=md5(token + salt)&s=salt`
  form, but only against the user's own *Subsonic token*, which a client had no way to get:
  `/muma/api/admin/subsonic-token` needs an administrator. New `GET /api/auth/subsonic-token`
  returns the caller's own token (the account the key resolves to, nothing in the request can name
  another), issuing one into LMS's `lms.db` when there is none and leaving an administrator-issued
  token as it is; the key check counts towards the login rate limit and the token is never logged.
  The web player now signs in through MuMa first (password in the POST body), fetches its token and
  signs every URL with it; the password is only the fallback while no token is known. LMS's `/muma`
  bridge accepts `u`/`t`/`s` too, checked like `/rest`, for the artist-image URLs. Bug report 103,
  closes GitLab issue #21.

<!-- release notes -->

- **Je wachtwoord staat niet meer in elk webadres naar de muziekserver.** De webspeler bewees wie
  je bent door je wachtwoord in de URL van elk nummer, elke hoes en elke lijst te zetten, en
  daarmee in elk logbestand onderweg. Nu krijgt elke gebruiker automatisch een eigen
  Subsonic-token en ondertekent de speler daarmee; het wachtwoord gaat alleen nog mee bij het
  inloggen zelf.
