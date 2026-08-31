# Running the disk janitor on a host

`scripts/ci/disk-janitor.sh` reclaims disk on a CI runner by removing Docker image tags nothing
needs. It is wired two ways, because the two runners cannot be reached the same way.

**The LXC (192.0.2.40) gets it from CI.** The `runner:disk-janitor` job is untagged, and untagged
jobs always land on the LXC — the workstation runner is tagged-only. Pipeline schedule 3 ("Daily CI
runner disk janitor", `develop`, `23 5 * * *` Europe/Amsterdam) sets `DISK_JANITOR` = `true`; every
other job steps aside via `.dedicated_schedule_guard`, so that pipeline runs the janitor and nothing
else. Nothing to install on the host.

The minute is deliberate: the hourly Renovate schedule runs at `:41` and the weekly downloader
refresh at 04:17, and a sweep landing on top of either would be refused images and a confusing log.

**Everything else gets the timer here.** A schedule cannot target the workstation (both runners
carry the `fast` tag, so tagging would be a coin flip), and it fills up too — mostly with buildkit
cache from local work rather than tags, which is exactly the case the script reports instead of
silently "fixing".

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

## Checking on it

```bash
systemctl list-timers muma-disk-janitor.timer
journalctl -u muma-disk-janitor.service -n 50
/opt/muma-disk-janitor/disk-janitor.sh --dry-run --force   # what would it remove right now
```

`--force` ignores the usage threshold; `--dry-run` prints the plan and removes nothing. Together
they are the safe way to ask "what does it think is disposable" on a host that is not full yet.

## Two passes

The normal pass is gentle on purpose — it keeps `:latest`/`:stable`, the 3 newest version tags per
repository and the 2 newest android-ci images, because an evicted image costs a rebuild or a pull
and on a merely-above-threshold host that is a bad trade.

If the disk is *still* at or above the critical mark afterwards, it escalates to keeping one of
each and sweeps again. That exists so the "tags are no longer the problem" message is true when it
appears: without it the script could declare tags innocent while a 9GB image sat there protected by
policy rather than by safety. Everything the escalation takes is still recoverable and still never
forced.

`--dry-run` prints both passes separately, so you can see what escalating would cost before it does.

## When it exits 1

That means it swept everything it can safely remove, escalation included, and the disk is still
critical. It is not a janitor failure, it is the janitor's finding: the space is in the buildkit
cache, in a runner build directory, or outside Docker entirely. On the workstation on 2026-08-31
that answer was correct and worth having — Docker held ~66GB of a 207GB-full disk, and the rest was
snap, an Android SDK and a stray 2.4GB crash dump. Pruning the build cache does free a lot and does cost the
ccache that keeps `muma-server:unit` at ~90s instead of ~405s — a trade to make deliberately, not a
cleanup step. The unit treats exit 1 as success so a persistent full disk does not fill the journal
with failed activations; the message is in the log either way.
