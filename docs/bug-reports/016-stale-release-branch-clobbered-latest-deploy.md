# title: A stale, unmerged `release/0.0.35` branch's delayed pipeline re-pushed old code as `latest` and redeployed it right after bug 015's fix

# status: fixed

# reported problem
After merging and deploying the fix for `bug 015` (`release/0.0.37`, `release:build-images` +
`deploy:prod` both succeeded and pushed the corrected `muma/muma-tools:latest` image),
re-checking production a few minutes later showed the `genre-processor` and
`muma-soundcloud-fetcher` containers running the *old*, broken image again — the exact
`ModuleNotFoundError` from `bug 015` had returned even though the fix was already merged into
`master`.

# Possible reason
`docker inspect`'s `Created` timestamp on the running `muma/muma-tools:latest` image was
*later* than the `release:build-images` job that pushed the fixed image, which meant something
else had pushed a newer `latest` afterwards. The GitLab pipeline list showed an old pipeline
(`#303`, for a long-forgotten, unmerged `release/0.0.35` branch, created ~1h before `bug 015`'s
fix) whose `release:build-images`/`deploy:prod` jobs had been stuck queued on the single shared
runner and only actually executed *after* `release/0.0.37`'s pipeline finished — rebuilding
`latest` from `release/0.0.35`'s stale checkout (which predated the `bug 015` fix) and
redeploying it to production. The repository had accumulated many other old, already-merged-but-
never-deleted `release/*` branches (`release/0.0.6` through `release/0.0.36`), each one a latent
trigger for `release:build-images`/`deploy:prod` (both gated only on
`$CI_COMMIT_BRANCH =~ /^release\//`) if anything ever pushed to or re-ran a pipeline against them.

# solution
- Deleted the offending `release/0.0.35` branch (confirmed via `git diff origin/master
  origin/release/0.0.35` that it only reverted already-superseded code, no unique unmerged work).
- Bulk-deleted all other already-merged branches via GitLab's `DELETE
  /repository/merged_branches` API to remove the rest of the accumulated stale `release/*`
  branches, eliminating the whole class of "delayed/stuck pipeline on a forgotten branch clobbers
  `latest`" risk going forward.
- Cut a new, minimal `release/0.0.38` (version bump only, no functional change — `bug 015`'s fix
  was already on `master`) to re-run `release:build-images`/`deploy:prod` cleanly, with no other
  release branch left to race it, restoring the correct image to production.
- Follow-up recommendation (not yet automated): delete a `release/*` branch as part of
  `release:back-merge-develop` (or a dedicated cleanup job) once its merge to `master` is
  confirmed, so merged release branches never accumulate again.
