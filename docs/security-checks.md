# Security and automatic checks, explained

This document explains which security and automatic code checks run in this repo. It says what each
one does and, above all, *why* it is set up that way. No jargon where it is not needed.

Read it to understand the checks. Do not use it as a list to tick off. If you later want to reverse a
choice, this is where the reasoning is.

---

## The common thread: a check you ignore is worse than no check

Almost every choice below comes down to the same thing. You can turn on a check that is red right away,
because there are already a hundred old problems. What happens next is predictable. Within a week,
everyone learns that red is normal, and the first real error goes unnoticed.

So this is how it works here:

1. Turn the check on.
2. Write down what is already wrong today, with a reason, in a file in the repo.
3. The check is green today. It turns red as soon as something **new** appears.

Such a written list is called a **baseline**. It is not a way to hide problems. The difference is that
every line has a reason, and a new problem does not slip in under it.

---

## CORS: who may call the API from a browser?

### What the problem is

When you open a website, the JavaScript on that page can send requests to other addresses. A browser
does not allow that by default. It first asks the receiving server: "may a page from site X call you and
read the answer?" That answer is called CORS.

The API was set to: **everyone may, with any method and any header.** In code:
`allow_origins=['*']`.

### Why that is not an immediate disaster

Your API is protected by a key in a header (`x-api-key`). A browser does not send that key by itself. An
attacker would already need the key, and then CORS would not help them. So CORS is not a way around
authentication.

### Why it had to go anyway

Not everything behind that API is protected. A public endpoint such as `/health` can be read without a
key. With CORS wide open, any website you visit while you are on your home network can read those
endpoints. Your browser then becomes the bridge into your own network.

### How it works now

The allowed origins come from a setting, `MUMA_CORS_ORIGINS`, a comma-separated list. If the setting is
not set, only the development addresses apply (`localhost:5173` and `localhost:5082`).

This works because almost nothing calls the API from another origin:

- The **web interface** is served by the LMS server, which passes `/api` on the *same* origin. With the
  same origin, CORS does not apply.
- The **Android app** is not a browser. CORS exists only in browsers, and the app never touches it.

**The way out, and it matters.** If there turns out to be a browser client I do not know about, set
`MUMA_CORS_ORIGINS=*`. The old behavior is back exactly. It needs no new rollout, only a restart. At
startup, the app writes to the log which case applies. So diagnosis is one look at the log, not a guess.

Details: `services/music_manager/cors.py`.

---

## Shellcheck: checks the shell scripts

### What it is

Shellcheck reads `.sh` files and points out errors that the shell itself only notices while it runs, or
never notices. Think of a variable without quotes that breaks on a space in a file name, or a comparison
that is always true.

### Why here

This repo has 65 shell scripts, and they do important work: they roll out to production, tag releases,
build images, and start every test run. No task ever checked them. An error in one of these scripts was
noticed when a rollout ran it, which is the most expensive place to find it.

### How it is set up

The bar is at **warnings**, with no exception list. At the start it was at errors, because 32 warnings
were open and the check would otherwise have been red on day one. Those warnings are fixed (issue #33).
A new warning now makes the job fail. If a warning is deliberate, that one line gets a
`# shellcheck disable=SCxxxx # <reason>`.

At the error level there was exactly one hit, and it is fixed. The install script for the Android app
compared a list of apps as one long pasted string. So a name that happened to occur inside another name
passed as valid.

Details: `scripts/shellcheck.sh`, job `muma:shellcheck`.

---

## SAST with semgrep: looks for known vulnerable patterns in the code

### What it is

SAST stands for *static application security testing*. A program reads your source code without running
it, and looks for patterns that are more often a security problem than not. Examples are an SQL query
built by pasting text together, a password in the code, or a container that runs as root.

We use **semgrep** with its default rule set.

### What it found here

It reported 232 findings when it was turned on. Important: **not one leaked key**. What did come out:

- **88 about SQL construction.** You cannot pass table and column names as parameters, because SQL does
  not allow that. So they are pasted into the text. Each place does that with an internal constant, not
  with anything from a request. The values do go through placeholders.
- **71 about container settings.** Running as root, a writable file system. One of these is fixed (see
  below). The rest is recorded.
- **40 about GitHub Actions** in files left over from the Ultrasonic days. Those were removed. This is a
  GitLab repo without a GitHub remote, so those workflows ran nowhere.
- **5 about `sshpass`.** They read a variable, not a hard-coded password. But it is a real weak point:
  a password passed as a command-line argument is visible to every other process on that machine. For
  a deploy script on your own workstation, that is acceptable.
- **1 about CORS.** Covered above, and fixed.

### How it is set up

This check **does block**. The dependency audit below does not. The reason is where the finding comes
from. A new security hole in a package can appear without anyone pushing anything. That is a matter of
the outside world. A SAST finding is about the change that is in place now.

All existing findings are in `security/accepted-sast-findings.txt`, with a reason per line. A second
identical line in the same place counts as new. "We do that elsewhere too" does not cover new code.

**A telling detail:** on its very first run, this task flagged a finding in the script that implements
it. I used SHA-1 for a fingerprint. That is technically harmless. But an exception as the first line in
a file whose job is to let nothing through is the wrong start. It uses SHA-256 now.

Details: `scripts/ci/sast.sh`, job `security:sast`.

---

## Detekt: checks the Kotlin code of the Android app

### What it is

Detekt is to Kotlin what shellcheck is to shell scripts. It reads the code and points out things that are
probably wrong or messy: functions that are too long, dead code, a file name that does not match what is
inside.

### Why it did nothing

Detekt had been in the build for a long time. But it sat behind a flag (`-Pqc`) that no job passed. So it
never ran, never failed, and nobody knew it was there.

### How it is set up now

It runs as part of the existing Android check. It has no job of its own. All Android jobs share one Gradle
working directory behind one lock, so a second job would only sit and wait.

The 74 existing findings (44 in the app, 30 in the Subsonic client) are in baselines per module. The one
finding in code from that same day was fixed, not recorded.

Details: `scripts/test/muma-mobile-detekt.sh`, included in `mobile:unit`.

---

## Gitleaks: looks for leaked passwords and keys

This ran before my time. Gitleaks scans the code for things that look like a key or a password.

This job is deliberately **not** `allow_failure`. Unlike the dependency audit, it does not depend on an
external service. So a failure is a finding, not an outage.

Exceptions per path are in `security/gitleaks.toml`. Exceptions per finding are in `.gitleaksignore`.
That last file contains no keys. It only holds references in the form `commit:file:line`. Semgrep flagged
the file itself. That was a false alarm.

---

## Dependency audit: checks the packages we rely on

### What it is

Every project depends on dozens of packages from other people. Security holes in those packages are found
regularly. This job compares what is installed with the public lists of known holes. It uses `pip-audit`
for Python and `npm audit` for the frontend.

### Why it may fail without blocking everything

It queries a database over the network. If that service is down for a moment, that is an outage, not a
finding. Master should not turn red because of it. That is why the job has `allow_failure`.

That does not make it optional. Exceptions are listed with a reason and an exit in
`security/accepted-vulnerabilities.txt`. There are 7 now. Most of them disappear together once FastAPI is
upgraded. That is a migration, not a version bump, so it deserves its own round.

The job also runs in the last stage of the pipeline, with `needs: []`. That sounds technical, but it is a
lesson we learned. The job once stood at the front and held up the whole test round for ten minutes, for
an outcome that blocks nothing. A job that must not hold up the pipeline must not slow it down either.

---

## Containers: `no-new-privileges`

All 46 services in the compose files now run with `no-new-privileges`. That stops a process inside a
container from gaining more rights than it started with, through a trick such as a setuid program. It
cannot break anything that works now. That is exactly why it could go in at once.

**What was deliberately not done:** the containers still run as root, with a writable file system. That
is 34 findings. Either change could fail in a way that only shows during a rollout. An example is a
service that writes a temporary file, or rights on a shared folder. Production cannot be tested here. The
findings are recorded, with that reason.

---

## Renovate: keeps dependencies up to date

Renovate automatically opens merge requests for newer package versions.

A new version has a **three-day waiting period** before it is proposed. A version published minutes ago
can still be withdrawn or turn out to be compromised. This project merges some of these updates
automatically.

There are two deliberate exceptions:

- **Security warnings** do not wait.
- **`yt-dlp` does not wait.** That package ships fixes for downloading as ordinary releases. Falling
  behind is exactly what breaks downloads. Waiting three days there means three days of failed downloads.

---

## What this does *not* cover

One thing matters more than the rest of this document, because it recently caused real pain.

**Nothing ever starts the Android app.** The pipeline builds the release APK and stops there. All Android
tests run on the JVM without shrinking. A bug that exists only in the shrunk release build passes through
unnoticed. That is exactly what happened with version 6.21.0: the app crashed on startup while every test
was green.

Closing that gap needs an emulator. The emulator needs `/dev/kvm` passed through to the runner LXC. That
is a resource trade-off, not a code change.

The `muma:e2e` job covers the server chain. A file on disk is scanned. It is then found again through the
same route the phone uses, and logged back to the track as a listen. The job was on manual for a long
time, because a full stack seemed expensive. Measured, it takes 45 to 90 seconds. So it now runs on every
pipeline and blocks. Almost all of that time is spent waiting for the three containers to report healthy.
That wait varies with how busy the runner is. The test itself takes 2 seconds. It does **not** cover the
app, and the top of that script says so too.

The middle part, whether the music server finds the track itself, only checked that an answer came back
until 2026-08-22. So it passed on a failed sign-in. Subsonic wraps errors in a successful HTTP response.
The test stack now first creates a user and waits until that user is applied. Then it registers the music
folder and runs a scan. Only after that does the test check the content of the answer. Since that same
date, the track is also actually fetched. The test checks that the file comes back byte for byte, with the
size the music server reports, so nothing was converted on the way. It also checks that a single byte from
the middle can be requested. That is what a player does when you skip into a track.

---

## Overview

| Check | Blocks? | Why |
|---|---|---|
| `backend:lint` / `backend:typecheck` | yes | Covers the code that is in place now |
| `muma:shellcheck` | yes, at warning level | No exception list; deliberate cases are switched off per line |
| `security:sast` | yes | The finding is about this change, not the outside world |
| `security:secret-scan` | yes | Does not depend on an external service |
| `security:dependency-audit` | no | Queries an external database; an outage is not a finding |
| `mobile:unit` (incl. detekt) | yes | Same reasoning as above |
| `muma:e2e` | yes | The only check that proves the whole chain, and it takes 45 to 90 s |

Open work arising from this lives in [GitLab issues](https://gitlab.example.org/example/music-management/-/issues) (see [docs/open-work.md](open-work.md)).
