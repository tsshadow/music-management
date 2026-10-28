- **A listener's e-mail address and account name are gone from the docs.** Bug report 020 and the
  Wrapped research note now use `user@example.org` and `listener-2`. A test in `tests/ci/` fails
  when the old values come back; it stores only their sha256 digests.
