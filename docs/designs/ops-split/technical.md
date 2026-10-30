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
| Deploy job (`muma:deploy`) | here | operations repository (`deploy:production`) |
| Deploy scripts (`scripts/ci-deploy.sh`, `prod-ssh-setup.sh`, `ssh_host_keys.sh`) | here | here until step 3b, read at the tag; then the operations repository |
| Post-deploy checks (`muma:verify`, `release:verify-deployed`, `verify-prod-version.sh`) | here | removed: `ci-deploy.sh` already ends in `post-deploy-verify.sh`, which checks the version |
| Image pruning on the host (`prune-prod-images.sh`) | here | here until step 3b, run by `ci-deploy.sh` |
| APK upload to the app download service | here | operations repository, after the check |
| Production CI variables (`PROD_*`, `APK_HOSTER_PASSWORD`) | here | operations repository; deleted here in step 3b. `APK_HOSTER_URL` stays: the app is built with it |

`scripts/deploy.sh` stays here because it is generic: it takes the stack name, the compose files
and the image tag from its environment, and a self-hoster runs it too. What makes a deploy
"production" (the SSH target, the two stacks, the nginx file for the LMS stack, the secrets) is
in `ci-deploy.sh`, and that file moves.

## Release Pipeline in This Repository

On `release/*`, nothing changes before the deploy stage. `mobile:build-release` keeps the signed
build and replaces the upload:

```
PUT /projects/:id/packages/generic/muma-mobile/<versionName>/muma-mobile-v<versionName>-<versionCode>.apk
PUT /projects/:id/packages/generic/muma-mobile/<versionName>/muma-mobile-v<versionName>-<versionCode>.txt
PUT /projects/:id/packages/generic/muma-mobile/<versionName>/muma-mobile-v<versionName>-<versionCode>-mapping.txt
```

The `.txt` file is the release notes the app download service shows. The job authenticates with
its own job token. A re-push of the release branch adds the files again, and a download returns
the newest, the same as it overwrites `:X.Y.Z` today.
The mapping file stays a job artifact too, for the crash triage.

On `master`:

1. `release:publish` (new, replaces `release:verify-deployed`,
   `scripts/ci/check-release-published.sh`): finds the push pipeline of the release branch head
   (the merge commit's second parent) and checks that `release:build-images` and
   `mobile:build-release` succeeded in it, then that the package holds the APK of the app's
   `versionName` and `versionCode`. A missing item fails the job, and no tag is set. No GitLab
   release object is made: nothing reads it.
2. `release:tag` needs `release:publish` and sets `release-vX.Y.Z` (and `muma-mobile-vA.B.C`).
   It stays the last write of the pipeline.
3. `release:cleanup-branch` and `release:back-merge-develop` are unchanged.

Removed: `muma:deploy`, `muma:verify`, `release:verify-deployed` and `verify-prod-version.sh`.
The `resource_group: production` and the `production` environment go with them. In step 3b,
`release:check-secrets` keeps only the keys the build needs (Docker Hub, signing, the
`VITE_*`/`MUMA_*` build values), and the image build stops reading `PROD_ENV_FILE`.

`muma:refresh-downloader` stays as it is and pushes `:latest` (functional open question 1): the
deploy still moves `:latest` to the release, and Watchtower picks up the weekly rebuild.

## Operations Repository

Files:

- `deploy/versions`: one line, `MUMA_VERSION=X.Y.Z`. The only file a deploy changes.
- `renovate.json`: a custom regex manager on `deploy/versions` with the `gitlab-tags`
  datasource for this repository, `extractVersion` `^release-v(?<version>.+)$`, `automerge: true`
  and `platformAutomerge: true`. An hourly pipeline schedule with `RENOVATE=true` runs it.
- `.gitlab-ci.yml`: the jobs below, on the default branch only, plus a validation job on MRs.
- The production CI variables, moved from this repository.

Pipeline on a commit to the default branch that changes `deploy/versions`:

1. `deploy:production` (`resource_group: production`, `deploy/fetch.sh` then the tag's own
   `scripts/ci-deploy.sh`): a sparse clone of this repository at `release-v$MUMA_VERSION` with the
   job token, so the recipe and the images have the same version. Same steps and order as before:
   disk check, verified dump, reconcile, tag promotion, `pull` and `up` of the changed services,
   `post-deploy-verify.sh` against the version, image pruning. It starts on its own when a commit
   to the default branch changes `deploy/versions`, and by hand otherwise.
2. `deploy:apk` (`deploy/apk-upload.sh`, needs `deploy:production`): downloads the APK and its
   release notes from the package registry and uploads them to the app download service. A
   version without a package (a release that did not change the app) exits 3, which is allowed.

On an MR the pipeline runs `deploy:fetch`, so an MR that names a version without a tag stays red
and does not merge.

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
3. This repository: add the package upload and `release:publish`, and remove the deploy jobs.
   Operations repository: the automatic deploy, `deploy:apk` and Renovate with automerge.
3b. Move `ci-deploy.sh` and its helpers to the operations repository, stop the image build
   reading `PROD_ENV_FILE`, and delete the production variables here.
4. First release on the new path. Check the four items of functional criterion 2 and the deploy.

## Data Model

None. The deploy writes no table. The reconcile is unchanged.

## API Contract

No application API changes. The contract between the repositories:

| Item | Producer | Consumer | Guarantee |
|---|---|---|---|
| Tag `release-vX.Y.Z` | `release:tag` | Renovate, `deploy/fetch.sh` | Exists only after the images and the package files below |
| Images `<image>:X.Y.Z` | `release:build-images` | `deploy` | Every image of `build-and-push-images.sh` |
| `muma-mobile/<versionName>/` package | `mobile:build-release` | `deploy:apk` | APK, release notes and mapping, signed with the release key |
| Files under `docker/` and `scripts/` at the tag | git | `fetch` | `scripts/deploy.sh` keeps its environment interface (`STACK_NAME`, `LOCAL_COMPOSE_FILE`, `LOCAL_ENV_FILE`, `REMOTE_HOST`, `IMAGE_TAG`, `SCHEMA_IMAGE_TAG`, `DEPLOY_PRE_UP_HOOK`) or the change is called out in the changelog as breaking |

## Cross-App Impact

None for the apps. Self-hosting docs (`docs/self-hosting.md`) lose the "deploy from GitLab CI"
section and get "install a release": pick a tag, render the compose files, run
`scripts/deploy.sh`.

## Technical Acceptance Criteria

1. After step 3b, `grep -rE 'PROD_REMOTE_HOST|PROD_SSH|APK_HOSTER_PASSWORD' .gitlab-ci.yml scripts/ci/`
   finds only `mobile:build-debug`.
2. A `master` pipeline with one image missing from the registry fails in `release:publish` and
   sets no tag.
3. For a version with an app bump, the package holds the APK, the release notes and the mapping,
   and `deploy:apk` uploads the APK.
4. In the operations repository, an MR that sets a version whose tag does not exist fails in
   `deploy:fetch`.
5. The change-over step 2 comparison shows equal containers and image ids.
6. A revert of the version commit deploys the previous version, and `/health` reports it.
7. `deploy:apk` does not run when `deploy:production` is red.

## Related Docs

- [declarative-schema](../declarative-schema/technical.md): the reconcile the deploy runs.
- [public-edition](../public-edition/technical.md): the variables that made the deploy
  configurable.
- `docs/self-hosting.md`: the install path for others.
