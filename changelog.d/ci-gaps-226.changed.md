- A release now fails its secrets check when `PROD_ENV_FILE_LMS` lacks `LMS_API_KEY`, `LMS_SUBSONIC_API_KEY` or `MUSIC_MANAGEMENT_API_KEY`; before, LMS deployed with an empty key and refused every call it should serve or make. Two release pipelines no longer push images at the same time (`release:build-images` has a resource group), a change to `requirements-dev.txt` runs format, lint and both type checks, and a change to `requirements.txt` builds the images on the merge request. `scripts/deploy.sh` refuses to run with `PORTAINER_WEBHOOK_URL` set, because a webhook recreated the stack before the backup and the schema step. The importer image no longer installs an unpinned `patool` on top of the pinned one in the base image.

<!-- release notes -->

- Release checks are stricter: a release stops when a player key is missing, and two releases can no longer publish images at the same time.
