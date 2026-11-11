- **A LAN host could give nginx a false client address.** nginx trusted `X-Forwarded-For` from
  10/8, 172.16/12 and 192.168/16, and publishes port 80 on every interface, so any host on the LAN
  could send a login with an address of its own choosing and start a fresh per-client rate-limit
  bucket with every guess. nginx now trusts loopback and the Docker networks (172.16.0.0/12), plus
  the addresses in the new `NGINX_TRUSTED_PROXY` setting of the player stack. An install behind a
  reverse proxy on the LAN, such as Nginx Proxy Manager, must set `NGINX_TRUSTED_PROXY` to that
  proxy's address, or every login through it counts against the proxy's own address (issue #234).
<!-- release notes -->
- **nginx trusts the client address only from the proxy you name.** Behind a reverse proxy on the
  LAN, set `NGINX_TRUSTED_PROXY` in the player stack's env to that proxy's address before you
  deploy, or all logins share one rate limit.
