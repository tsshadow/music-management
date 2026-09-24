- **The web login hands each user their own MuMa key instead of LMS's shared `api-key`.** LMS
  answered `/muma/api/auth/login` itself and returned its own configured `api-key` to every user --
  on production possibly MuMa's system key, which MuMa treats as an always-allowed superuser and the
  web app showed as an administrator for whoever held it. The route is now MuMa's own login: nginx
  sends it to `music-manager` directly (and LMS, when reached without nginx, passes it through), so
  the answer is `{api_key, refresh_token, user: {permissions, role_name, is_admin, ...}}` for that
  user. **Contract change:** a client that read LMS's flat `{id, username, display_name, is_admin,
  api_key}` gets MuMa's shape instead; the web player is updated in the same change and MuMa Mobile
  already used MuMa's login. **Every web user signs in once more:** a browser still holding the
  shared key finds it verified as a system key at startup, and the session ends instead of counting
  as an administrator. On the direct route nginx forwards the client as one `X-Forwarded-For`
  address (the right-most one not written by a private-network proxy), so the login rate limit
  cannot be reset by a forged address in front of the chain.

<!-- release notes -->

- **Signing in on the web now gives you your own key, not one shared by everybody.** What the
  management screens let you do follows your own account. Everyone signs in once more after this
  update.
