- **Every user route existed twice.** The users router was mounted at `/api/users` and again at
  `/api` (to reach `/api/auth/*`), so `DELETE /api/{user_id}` and every other user route answered under the
  bare prefix too. The session endpoints (`/api/auth/*`) and `GET /api/roles`, which the web
  player's Beheer page calls there, are now a router of their own at `/api`; everything else is under
  `/api/users` only. No client used the duplicates. `/api/users/auth/*`, which
  `docs/api-specification.md` documented and no client called, no longer exists.
- **The analytics, config, feeds, stats and listening routers check a key through the one
  `users.verify_api_key`**, as scanner already does (management and rating follow in !916). A user key no account
  holds, or a disabled account, now gets that function's 403 there instead of a local copy's 401;
  a missing key is still a 401. The web player treats both the same.
- **`docker/docker-compose.workers.yml` is marked local-only** (`scripts/dev.sh` layers it on top;
  production never reads it), and `run_telegram_auth.sh` points at `docker/docker-compose.yml`
  instead of a `work-context/` file that no longer exists.
