# Back-Merge Commits Fail The Public History Check

# status: fixed

# reported problem
From 2026-11-06, `public:history` failed on every develop pipeline. It flagged four commits, each with the message "Merge branch 'master' into 'develop'", for identity and pattern.

# Possible reason
`release:back-merge-develop` opened a merge request from master to develop and merged it through the API, often with auto-merge. GitLab then writes the merge commit as the user of the token. For a project access token that is a bot user, and the address of a bot user names the private GitLab host. The identity policy in `scripts/ci/public_guard.py` refuses that address, and the host is one of the patterns. Older back-merge commits have the neutral identity, because the history rewrites of 2026-10-29 and 2026-11-04 replaced it. The release tags had the same problem and were fixed in issue #207.

# solution
`scripts/ci/back-merge-develop.sh` makes the merge commit with git, as `ci-release-tagging <ci-release-tagging@users.noreply.example.com>`, and pushes it to develop with the project token. It tries three times when develop moves, and it fails without a push on a conflict. `tests/ci/test_back_merge_develop.py` covers the identity, a second run and a conflict. The four commits from before the fix stay in the history until a person decides how to clean them.
