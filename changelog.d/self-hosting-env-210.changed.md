- **A copied `.env.example` now renders the compose file without an unset variable.** The workers'
  `AUTH_SERVICE_URL` was the last one missing; a new host got workers that could not announce a
  tagged file. `docs/self-hosting.md` also says which folder names under the music root the tagger
  walks: a download written elsewhere is never tagged (#210).
