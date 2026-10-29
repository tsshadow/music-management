# Build cache filled the workstation runner and a release skipped its deploy

# status: fixed

# reported problem

On 2026-09-25 `mobile:smoke` in release pipeline 3607 failed on the workstation runner
(`minipc-debian13-192.0.2.227`, the second `fast` runner). The emulator stopped with:

```
FATAL | Not enough space to create userdata partition. Available: 3732.78 MB ... need 7372.80 MB
```

`mobile:smoke` runs before `muma:deploy`, so the release was never deployed. Nothing in the log
said "disk". It read like an emulator or image problem.

`/var/lib/docker` is a separate 183GB partition on that machine, and it was 98% full.
`docker system df` showed 124GB of build cache (1732 entries) and 43.6GB of images. Pruning the
cache by hand with an age filter (`docker builder prune -f --filter until=72h`) freed 62GB.

# Possible reason

Both runners already had a janitor (`scripts/ci/disk-janitor.sh`, MR !528). The LXC runs it from
the `runner:disk-janitor` schedule, the workstation from a systemd timer. The timer had run that
same morning at 04:05. But the script only removed image tags. It left the BuildKit build cache
alone on purpose, because an unfiltered `docker builder prune` also empties the ccache that keeps
`server:unit` at about 90s instead of about 405s. The script told a person to decide about the
cache. On the workstation nobody read the journal, so the cache grew until a job failed.

The emulator job had no free-space check of its own. The first sign of a full disk was a FATAL
from qemu, minutes into the job.

# solution

- `disk-janitor.sh` now prunes build cache on every sweep, always with an age filter:
  `docker builder prune -f --filter until=<N>h`. The default is 72 hours (`--cache-max-age`, or
  `DISK_JANITOR_CACHE_MAX_AGE_HOURS`). BuildKit measures `until` from an entry's last use, so the
  ccache that recent `server:unit` runs used stays. This pass runs before the image passes, and if
  it brings the disk below the target, no image tag is touched.
- If the disk is still at 85% or more after the image passes, it prunes cache not used in the last
  24 hours (`--cache-floor-age`, or `DISK_JANITOR_CACHE_FLOOR_AGE_HOURS`). It never prunes without
  an age filter. An age of 0, an empty age, or a non-number is refused, because each would mean
  "everything".
- Nothing else changed in what may be deleted. The 3 newest `muma/*` version tags per
  repository and `:latest`/`:stable` are kept. There is still no container, volume or system
  prune, and no `rmi -f`. Each run now prints `df` and `docker system df` before and after.
- `mobile:smoke` runs `scripts/ci/docker_disk_preflight.py` before it starts the emulator. With
  less than `EMULATOR_MIN_FREE_GB` (default 12) free on the Docker data root, the job fails at once
  and names the fix: `./scripts/ci/disk-janitor.sh --force` on that runner.
- `tests/ci/test_disk_janitor_script.py` reads the script and checks two things. Every builder
  prune has an age filter, and there is no container, volume or system prune, no `rmi -f` and no
  `image prune -a`. It also runs the real script against a fake `docker` and `df` to check which
  passes run at which disk level. `tests/ci/test_docker_disk_preflight.py` covers the pre-flight.

The timer on the workstation runs a copy in `/opt/muma-disk-janitor/`. That copy has to be
installed again before the workstation gets the cache prune (`scripts/ci/systemd/README.md`). This
is tracked in the open GitLab issues.
