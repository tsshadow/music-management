- **Owner-only agent rules moved out of `AGENTS.md`.** The host-specific parts (production host and its
  runbook pointers, the password-manager wrapper, the owner's issue board and labels, the self-hosted push
  server) now live in the private `AGENTS.private.md`, which `muma-ops/install.sh` links as
  `AGENTS.local.md`. The public rules 14 and 16 are generic. `services/muma-mobile/.junie/` moved to
  muma-ops too, and `.production` is ignored by path and covered by the not-tracked test. Refs #189.
