# Ops Split: Technical Design

Implements [functional.md](functional.md). The contract between the two repositories is one git
tag, `release-vX.Y.Z`, and what exists when it exists. This repository never calls the operations
repository, and the operations repository reads this one only at a tag.

## What Stays, What Moves

| Part | Today | After |
|---|---|---|
| Image build and push (`release:build-images`, `build-and-push-images.sh`) | here, on `release/*` | here, unchanged: `:X.Y.Z` and `:rc` |
| Signed APK build (`mobile:build-release`) | here, uploads to the app download service | here, uploads the APK and mapping to the GitLab package registry |
| Tag (`release:tag`) | here, after `release:verify-deployed` checked production | here, after `release:publish` checked that every image and the APK exist |
| Compose files (`docker/`), `scripts/deploy.sh`, `schema_reconcile` | here | here: they are the install recipe of a version and are read at its tag |
| Deploy job (`muma:deploy`, `scripts/ci-deploy.sh`, `prod-ssh-setup.sh`, `ssh_host_keys.sh`) | here | operations repository |
| Post-deploy checks (`muma:verify`, `post-deploy-verify.sh`, `release:verify-deployed`, `verify-prod-version.sh`) | here | operations repository |
| Image pruning on the host (`prune-prod-images.sh`) | here | operations repository |
| APK upload to the app download service | here | operations repository, after the check |
| Production CI variables (`PROD_*`, `APK_HOSTER_*`) | here | operations repository; deleted here at the end |

`scripts/deploy.sh` stays here because it is generic: it takes the stack name, the compose files
and the image tag from its environment, and a self-hoster runs it too. What makes a deploy
"production" (the SSH target, the two stacks, the nginx file for the LMS stack, the secrets) is
in `ci-deploy.sh`, and that file moves.

## Release Pipeline in This Repository

On `release/*`, nothing changes before the deploy stage. `mobile:build-release` keeps the signed
build and replaces the upload:

```
PUT /projects/:id/packages/generic/muma-mobile/<versionName>/muma-mobile-<versionName>.apk
PUT /projects/:id/packages/generic/muma-mobile/<versionName>/muma-mobile-<versionName>-mapping.txt
```

A re-push of the release branch overwrites both files, the same as it overwrites `:X.Y.Z` today.
The mapping file stays a job artifact too, for the crash triage.

On `master`:

1. `release:publish` (new, replaces `release:verify-deployed`): checks with
   `docker manifest inspect` that each image in `build-and-push-images.sh` exists as `:X.Y.Z`,
   and, when the merge bumped the app, that both package files exist. Then it creates the GitLab
   release `release-vX.Y.Z` with the release notes and links to the two package files. A missing
   item fails the job, and no tag is set.
2. `release:tag` needs `release:publish` and sets `release-vX.Y.Z` (and `muma-mobile-vA.B.C`).
   It stays the last write of the pipeline.
3. `release:cleanup-branch` and `release:back-merge-develop` are unchanged.

Removed: `muma:deploy`, `muma:verify`, `release:verify-deployed` and their scripts. The
`resource_group: production` and the `production` environment go with them.
`release:check-secrets` keeps only the keys the build needs (Docker Hub, signing, the
`VITE_*`/`MUMA_*` build values).

`muma:refresh-downloader` pushes `:X.Y.Z-refresh.N` for the version on `master` instead of
`:latest` (functional open question 1). The operations repository's Renovate sees it through the
Docker datasource for the downloader image and treats it as a patch.

## Operations Repository

Files:

- `deploy/versions`: one line, `MUMA_VERSION=X.Y.Z`, plus `MUMA_DOWNLOADER_TAG` for the
  refresh tag. The only file a deploy changes.
- `renovate.json`: a custom regex manager on `deploy/versions` with the `gitlab-tags`
  datasource for this repository, `extractVersion` `^release-v(?<version>.+)$`, `automerge: true`
  and `platformAutomerge: true`. Hourly schedule.
- `.gitlab-ci.yml`: the jobs below, on the default branch only, plus a validation job on MRs.
- The production CI variables, moved from this repository.

Pipeline on a commit to the default branch that changes `deploy/versions`:

1. `fetch`: downloads `docker/`, `scripts/deploy.sh`, `scripts/lib/` and the LMS compose and
   nginx files from this repository at `release-v$MUMA_VERSION` through the repository archive
   API. The recipe and the images then have the same version.
2. `deploy` (`resource_group: production`): today's `ci-deploy.sh`, pointed at the fetched
   files. Same steps and order: disk check, verified dump, reconcile with
   `SCHEMA_IMAGE_TAG=$MUMA_VERSION`, tag promotion, `pull` and `up` of the changed services.
3. `verify`: today's `post-deploy-verify.sh` and `verify-prod-version.sh` against
   `$MUMA_VERSION`. Red sends an ntfy alert.
4. `apk`: downloads the APK from the package registry and uploads it to the app download service.
   Runs only after `verify` is green.
5. `prune`: today's image pruning.

On an MR the pipeline runs `fetch` and a `docker-compose config` of the fetched files with the
production env, so an MR whose recipe does not render stays red and does not merge.

Rollback: `git revert` of the version commit. The pipeline fetches the older tag's recipe and
deploys it. The reconcile only adds, so a rollback never removes a column that the newer version
added.

## Change-Over Order

1. Operations repository: add `deploy/versions` at the running version, the pipeline, and the moved
   variables. Until step 3 the deploy job runs the release's own `scripts/ci-deploy.sh` from the
   fetched tag, so it is the same code as `muma:deploy`, and it is manual. Run it by hand for the
   version that already runs. Expected: no container changes, reconcile "schema in sync".
2. Next release: deploy by the old path from this repository as usual, then set `deploy/versions` to
   the same version in the operations repository and run its pipeline. Compare `docker ps` and the
   image ids from both runs; they must be equal (functional criterion 7).
3. This repository: add the package upload and `release:publish`, remove the deploy jobs and
   their scripts, and remove the production variables. Turn on Renovate automerge in the
   operations repository.
4. First release on the new path. Check the four items of functional criterion 2 and the deploy.

## Data Model

None. The deploy writes no table. The reconcile is unchanged.

## API Contract

No application API changes. The contract between the repositories:

| Item | Producer | Consumer | Guarantee |
|---|---|---|---|
| Tag `release-vX.Y.Z` | `release:tag` | Renovate, `fetch` | Exists only after the images and the package files below |
| Images `<image>:X.Y.Z` | `release:build-images` | `deploy` | Every image of `build-and-push-images.sh` |
| `muma-mobile/<versionName>/` package | `mobile:build-release` | `apk` | APK and mapping, signed with the release key |
| Files under `docker/` and `scripts/` at the tag | git | `fetch` | `scripts/deploy.sh` keeps its environment interface (`STACK_NAME`, `LOCAL_COMPOSE_FILE`, `LOCAL_ENV_FILE`, `REMOTE_HOST`, `IMAGE_TAG`, `SCHEMA_IMAGE_TAG`, `DEPLOY_PRE_UP_HOOK`) or the change is called out in the changelog as breaking |

## Cross-App Impact

None for the apps. Self-hosting docs (`docs/self-hosting.md`) lose the "deploy from GitLab CI"
section and get "install a release": pick a tag, render the compose files, run
`scripts/deploy.sh`.

## Technical Acceptance Criteria

1. `grep -rE 'PROD_REMOTE_HOST|PROD_SSH|APK_HOSTER' .gitlab-ci.yml scripts/` finds nothing.
2. A `master` pipeline with one image missing from the registry fails in `release:publish` and
   sets no tag.
3. The GitLab release for a version with an app bump links both package files, and both download.
4. In the operations repository, an MR that sets a version whose tag does not exist fails in
   `fetch`.
5. The change-over step 2 comparison shows equal containers and image ids.
6. A revert of the version commit deploys the previous version, and `/health` reports it.
7. The `apk` job does not run when `verify` is red.

## Related Docs

- [declarative-schema](../declarative-schema/technical.md): the reconcile the deploy runs.
- [public-edition](../public-edition/technical.md): the variables that made the deploy
  configurable.
- `docs/self-hosting.md`: the install path for others.
