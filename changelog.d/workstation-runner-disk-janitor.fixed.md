- **A full build cache on the workstation runner skipped a release deploy.** On 2026-09-25,
  124GB of BuildKit cache filled `/var/lib/docker` to 98%. The emulator in `mobile:smoke` then
  failed on "Not enough space to create userdata partition", so `muma:deploy` never ran. The disk
  janitor used to leave the build cache alone completely. It now prunes cache that has not been
  used for 72 hours, and cache unused for 24 hours if the disk is still at 85% or more. It never
  prunes without an age filter, so the `server:unit` ccache stays. `mobile:smoke` also checks free
  space before it starts the emulator (12GB by default). When there is not enough, it fails at once
  and says how to fix it (bug report 073).
<!-- release notes -->
- A CI runner that was full of old build cache no longer blocks a release deploy. The cleanup job
  now also removes build cache that has not been used for days. The Android smoke test says
  clearly when the disk is too full, instead of failing with an unclear emulator error.
