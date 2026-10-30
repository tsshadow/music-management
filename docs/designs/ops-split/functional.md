# Ops Split: Functional Design

## Overview

A release of this repository builds the images and the app, and then deploys them to one
production installation. The deploy step knows that installation: its host, its container names,
its folders and its secrets. A self-hoster who forks the repository gets a pipeline that deploys
to a server they do not have.

This design moves the deploy out of this repository. The repository builds, tests and publishes.
A separate operations repository, owned by whoever runs an installation, decides when to install a
published release and does the install.

What a release gives:

- Docker images tagged with the version, for example `muma-core:0.95.0`.
- The signed APK and its R8 mapping file, attached to the GitLab release of that version.
- The tag `release-v0.95.0`. The release pipeline sets it last, so a tag means that every image
  and the APK for that version exist.

What the operations repository does with it:

- A bot (Renovate) sees the new tag and opens a merge request that changes one line: the
  installed version.
- The merge request merges itself when its pipeline is green.
- The pipeline on the merged commit deploys: database dump, schema reconcile, start of the new
  containers, a check of `/health`, and the APK upload to the app download service.
- To go back a version, revert that one-line commit. The pipeline deploys the version from before.

The installed version is then always the version in the latest commit of the operations
repository. Nothing in this repository needs to know where that installation is.

## User Stories

- As the developer, I want a release to end when the images and the APK are published, so that a
  release cannot fail on a production problem that has nothing to do with the code.
- As the operator, I want a new release to install itself after a green pipeline, so that I do
  not start each deploy by hand.
- As the operator, I want to see which version runs, and when it changed, in one file with a git
  history, so that "what is live" has one answer.
- As the operator, I want to go back one version with a revert, so that a rollback uses the same
  path as a deploy.
- As a self-hoster, I want the repository to publish images and an example compose file, without
  a deploy job for a host I do not have.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| The release MR merges to `master` | The pipeline tags `release-vX.Y.Z` and creates the GitLab release with the APK and mapping attached. Nothing is deployed from this repository. |
| A tag `release-vX.Y.Z` appears | Within one Renovate run, the operations repository has an MR "Update music-management to X.Y.Z". |
| That MR's pipeline is green | The MR merges. The pipeline on the merged commit deploys X.Y.Z, checks `/health`, and uploads the APK. |
| The deploy fails before the containers change (dump, reconcile) | The pipeline stops red. The previous version still runs. The version file says X.Y.Z, so the operator fixes the cause and retries the job, or reverts the commit. |
| The deploy fails after the containers changed (`/health` reports the wrong version or is red) | The pipeline stops red and sends an alert. The operator reverts the commit, which deploys the previous version. |
| A release is tagged but one image is missing | Cannot happen by design: the tag is set only after every image and the APK are published. A deploy that cannot pull an image fails before the containers change. |
| Two releases are tagged before the bot runs | The bot opens one MR for the newest version. The version in between is skipped. |
| The operator wants to hold a version | The operator closes the MR or sets the Renovate rule for this package to manual. Production stays where it is. |

## Acceptance Criteria

1. This repository has no CI job that connects to a production host, and no CI variable that
   names one.
2. A merge to `master` produces the tag, the GitLab release with the APK and the mapping, and the
   images with the version tag, in that order: the tag is the last of the four.
3. In the operations repository, a new tag leads to an MR that changes only the version file,
   and that MR merges itself after a green pipeline.
4. The deploy pipeline in the operations repository does the same steps, in the same order, as
   `scripts/deploy.sh` does today: dump, reconcile, start, check.
5. A revert of the version commit deploys the previous version, with no other step.
6. The APK reaches the app download service only after `/health` reports the new version, so the
   app never runs against an older server than it was built for.
7. During the change-over, a release can be deployed by the old path and by the new path, and
   both give the same running containers.

## Open Questions

1. The weekly image refresh (`muma:refresh-downloader`) rebuilds the downloader images from
   `master` for a new yt-dlp, as `:latest`, and Watchtower pulls them. With pinned versions,
   `:latest` is no longer what runs. Proposal: the refresh pushes a new tag `X.Y.Z-refresh.N` and
   the bot treats it as a patch update, so a refresh is a version commit like any other.
2. How fast must a release reach production? Renovate runs once a day in this repository today.
   The operations repository can run it hourly, or the release pipeline can trigger a run, at the
   cost of one call from this repository to the other. Proposal: hourly in the operations
   repository, no trigger, so the two stay apart. A release then waits one hour at most.
3. The nightly production check lives in the operations repository already. It gets one more
   item: an open, unmerged version MR older than one day.
