- **The test gates now measure what they claim.** Python coverage is measured on source only — the
  ~220 test files under `services/` used to count as covered code, and `tools/` was not measured —
  which moves the figure from 95% to 84.9% and the floor from 93 to 84; the only time that floor
  has gone down. `backend:integration` fails instead of skipping when CI cannot reach its database,
  and runs MariaDB 13.0 like production (`MARIADB_VERSION=10.6` still reproduces bug report 039).
  The loose mypy floor runs in a new `backend:typecheck-all` job (allowed to fail while its 299
  errors are worked down), and `scripts/lint.sh` now fails an undocumented public function or class
  in a strictly type-checked module. Bug report 047.

<!-- release notes -->
- Internal: the automated checks are stricter and report honest numbers.
