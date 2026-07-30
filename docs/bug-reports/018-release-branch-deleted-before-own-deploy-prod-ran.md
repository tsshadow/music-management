# title: `release/x.y.z`'s own `deploy:prod` job can fail because its branch is deleted mid-pipeline by a duplicate, faster "head pipeline" merging early

# status: fixed (worked around by re-cutting a fresh release branch; root cause below is not yet hardened)

# reported problem
While shipping `release/0.0.41` (the artist-images-black fix), the full branch pipeline (which
includes `release:build-images`, `ultrasonic:build-release`, and `deploy:prod`) was still running
`release:build-images` when the merge request into `master` had *already* merged. `deploy:prod`
subsequently failed with:
```
fatal: couldn't find remote ref refs/heads/release/0.0.41
ERROR: Job failed: exit status 128
```
`master`/`develop` ended up with the correct code and a `release-v0.0.41` tag, but production was
never actually redeployed with it.

# Possible reason
Every branch push in this project's GitLab setup produces **two separate pipelines** for the same
commit: a small one (only ran `contracts` + `lms:unit` here) and the "real", full one (everything
else, including `release:build-images`/`ultrasonic:build-release`/`deploy:prod`). This was already
observed once before, while shipping `release/0.0.40` (worked around there by explicitly identifying
and monitoring the correct pipeline ID before merging).

The merge request's `head_pipeline` — the pipeline GitLab actually considers when the MR becomes
mergeable/green — was the **small, fast one**. Something (unclear exactly what triggered it, no
`merge_when_pipeline_succeeds` flag was left set afterward) merged MR !78 into `master` as soon as
that small pipeline succeeded, at `07:33:01`, while the full pipeline's `release:build-images` job
was still running (finished only around `07:33:56`). Merging into `master` triggers `release:tag`
+ `release:back-merge-develop` on `master`'s own pipeline, and the latter — per its bug-016 fix —
auto-deletes the just-merged `release/*` branch. By the time the full pipeline reached its `deploy`
stage, `release/0.0.41` no longer existed on the remote, so the runner's `git fetch`/checkout for
`deploy:prod` failed outright before the script itself even ran.

This is a different failure mode from bug 016 (a *stale, unrelated* old branch's delayed pipeline
overwriting a newer deploy) — here it's a release branch's *own* pipeline racing its own branch
deletion, caused by GitLab associating the MR's mergeability with the wrong (duplicate, partial) of
the two pipelines running for the same commit.

# solution (workaround applied)
Cut a fresh release (`release/0.0.42`, no functional code change) from `master` (which already had
the fix and the correct `VERSION`/`CHANGELOG.md` state) to get a clean `deploy:prod` run against a
branch that isn't at risk of being deleted mid-flight, mirroring the same "re-deploy" pattern bug
016 already used (`d54cd1f18`, "Re-deploy bug 015 fix after stale release/0.0.35 branch clobbered
latest deploy").

**Not yet fixed**: the root cause (two pipelines per push, MR mergeability tied to the wrong one)
still exists and can recur on any future release. Worth a follow-up to either (a) understand and
eliminate the duplicate-pipeline trigger (likely both a branch pipeline and a merge-request pipeline
running for the same push — a common GitLab misconfiguration, usually fixed by adding `workflow:
rules` to `.gitlab-ci.yml` to prevent duplicate pipelines), or (b) make `release:back-merge-develop`
only delete a `release/*` branch after confirming `deploy:prod` actually succeeded *for that same
commit*, not just that *a* merge into `master` happened.
