# changelog.d — one file per change

`CHANGELOG.md` is not edited on a feature branch any more. Drop a fragment here instead; the
release assembles them.

## Why

Every branch used to append to the same `## [Unreleased]` block, and git merges that badly in two
different ways. The loud way is a conflict, which at least tells you. The quiet way is worse: when
a release ships while your branch is open, the three-way merge sees "we added entries" and "they
inserted a two-line version heading" and applies both — so your entries end up filed under a
version that went to production without them, with no conflict to warn you. That has happened to
four branches in one session, and nothing catches it: no test reads the changelog, and
`release-version-check.sh` only asserts that a dated entry for `VERSION` exists, not that its
contents are right.

A fragment is a new file with a name nobody else uses, so there is nothing to merge.

## Writing one

    changelog.d/<slug>.<section>.md              -> root CHANGELOG.md + RELEASE_NOTES.md
    changelog.d/mobile/<slug>.<section>.md       -> services/muma-mobile/ (both files and both
                                                    copies under app/src/main/assets/)

`<slug>` is anything unique — the MR number is the obvious choice (`619.fixed.md`), a short
description works too. `<section>` is one of `added`, `changed`, `deprecated`, `removed`, `fixed`,
`security`, which is the Keep a Changelog set and the order they are emitted in.

The body is the changelog entry itself, as one or more `-` bullets, in the voice the rest of
`CHANGELOG.md` uses: what broke or changed, what the reader would otherwise have concluded, and the
number that settles it.

`RELEASE_NOTES.md` says the same thing in fewer words and without the code detail, so a fragment
may carry a second version below a `<!-- release notes -->` line. Leave it out and the changelog
text is used for both.

```markdown
- **Een archief met één rare bestandsnaam liet de helft van zijn releases nooit binnen.** patool
  koos `unrar-free`, en die breekt de héle extractie af bij de eerste naam die hij niet naar de
  locale van de container kan omzetten. 13 van de 44 releases stonden op schijf.

<!-- release notes -->

- **Een archief met een enkele rare bestandsnaam liet de helft van zijn releases nooit binnen.**
  De importer probeert nu een andere uitpakker zodra de eerste faalt.
```

## What happens at release time

`scripts/release/assemble_changelog.py --version x.y.z` writes the fragments into a new
`## [x.y.z] - <date>` heading, writes the `RELEASE_NOTES.md` block, and deletes the files it used.
That runs as part of the stabilize commit on `release/x.y.z`, so `CHANGELOG.md` only ever changes
on a release branch — which is exactly what makes the misfiling above impossible.

`muma:changelog` fails a merge request that adds no fragment. If a change genuinely does not
deserve a line — a typo fix, a baseline bump — put the `no-changelog` label on the merge request.
