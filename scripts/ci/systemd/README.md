# Running the disk janitor on a host

`scripts/ci/disk-janitor.sh` reclaims disk on a CI runner by pruning build cache nothing has used
for 72 hours and removing Docker image tags nothing needs. It is wired two ways, because the two runners cannot be reached the same way.

**The LXC (192.0.2.40) gets it from CI.** The `runner:disk-janitor` job is untagged, and untagged
jobs always land on the LXC — the workstation runner is tagged-only. Pipeline schedule 3 ("Daily CI
runner disk janitor (every 3h)", `develop`, `23 */3 * * *` Europe/Amsterdam) sets `DISK_JANITOR` = `true`; every
other job steps aside via `.dedicated_schedule_guard`, so that pipeline runs the janitor and nothing
else. Nothing to install on the host.

The minute is deliberate: the hourly Renovate schedule runs at `:41` and the weekly downloader
refresh at 04:17, and a sweep landing on top of either would be refused images and a confusing log.

Three-hourly rather than daily, because the pressure is not nightly. On 2026-08-31 the LXC went
from 59% to 84% between midday and late afternoon on a day of heavy merging, and a 05:23 sweep
would have run when there was least to collect. The script is a no-op below its threshold, so the
extra runs cost a `df` and a `docker images`.

**Everything else gets the timer here.** A schedule cannot target the workstation (both runners
carry the `fast` tag, so tagging would be a coin flip), and it fills up too — mostly with buildkit
cache rather than tags. On 2026-09-25 124GB of build cache took `/var/lib/docker` to 98% and the
emulator in release pipeline 3607 could not create its userdata partition
([bug report 073](../../../docs/bug-reports/073-workstation-runner-build-cache-fills-disk.md)).
Until then the script left the cache alone entirely; it now prunes cache unused for 72 hours on
every sweep, and cache unused for 24 hours when the disk is still critical.

**The timer runs a copy.** `/opt/muma-disk-janitor/` is not a checkout, so a change to the script
reaches the workstation only when the install commands below are run again.

## Installing the timer

The script needs only its Python helper beside it, so there is no checkout to keep on the host:

```bash
sudo install -d /opt/muma-disk-janitor
sudo install -m 0755 scripts/ci/disk-janitor.sh /opt/muma-disk-janitor/
sudo install -m 0755 scripts/ci/disk_janitor_plan.py /opt/muma-disk-janitor/
sudo install -m 0644 scripts/ci/systemd/muma-disk-janitor.service /etc/systemd/system/
sudo install -m 0644 scripts/ci/systemd/muma-disk-janitor.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now muma-disk-janitor.timer
```

Set `User=` in the unit to whichever account can talk to the Docker socket on that host — the unit
ships with `gitlab-runner`, which is wrong on a workstation (`user` there). Neither needs root.

Create `/etc/muma-disk-janitor.env` with `DOCKER_USER=<registry user of the release images>`; the unit
reads it. Without it the janitor still prunes build cache, `android-ci` and `muma-test-*` images, and
logs a warning that old release image tags were not pruned.

## Checking on it

```bash
systemctl list-timers muma-disk-janitor.timer
journalctl -u muma-disk-janitor.service -n 50
/opt/muma-disk-janitor/disk-janitor.sh --dry-run --force   # what would it remove right now
```

`--force` ignores the usage threshold; `--dry-run` prints the plan and removes nothing. Together
they are the safe way to ask "what does it think is disposable" on a host that is not full yet.

## The passes

First, build cache not used in the last 72 hours (`--cache-max-age`, or
`DISK_JANITOR_CACHE_MAX_AGE_HOURS`). BuildKit measures `until` from an entry's last use, so the
ccache a recent `server:unit` touched stays. If that alone brings the disk down to the target, no
image tag is touched.

Then the image passes. The normal pass is gentle on purpose — it keeps `:latest`/`:stable`, the 3 newest version tags per
repository and the 2 newest android-ci images, because an evicted image costs a rebuild or a pull
and on a merely-above-threshold host that is a bad trade.

If the disk is *still* at or above the critical mark afterwards, it escalates to keeping one of
each and sweeps again. That exists so the "tags are no longer the problem" message is true when it
appears: without it the script could declare tags innocent while a 9GB image sat there protected by
policy rather than by safety. Everything the escalation takes is still recoverable and still never
forced.

Last, and only if the disk is still critical after that: build cache not used in the last 24
hours (`--cache-floor-age`, or `DISK_JANITOR_CACHE_FLOOR_AGE_HOURS`). Every builder prune carries an
age filter. An unfiltered one empties the ccache, and `tests/ci/test_disk_janitor_script.py` fails
on it. So does any container, volume or system prune.

`--dry-run` prints every pass separately, so you can see what escalating would cost before it does.
Each real run prints `df` and `docker system df` before and after.

## When it exits 1

That means it swept everything it can safely remove, escalation and the 24-hour cache floor
included, and the disk is still critical. It is not a janitor failure, it is the janitor's finding:
the space is in build cache used within the last day, in a runner build directory, or outside
Docker entirely. On the workstation on 2026-08-31
that answer was correct and worth having — Docker held ~66GB of a 207GB-full disk, and the rest was
snap, an Android SDK and a stray 2.4GB crash dump. Pruning the remaining build cache does free a lot and does cost the
ccache that keeps `server:unit` at ~90s instead of ~405s — a trade to make deliberately, not a
cleanup step. The unit treats exit 1 as success so a persistent full disk does not fill the journal
with failed activations; the message is in the log either way.
