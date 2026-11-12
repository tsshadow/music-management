# Music Mirror

A nightly copy of the music library on a second NAS, which never deletes and keeps ZFS snapshots.
The design and the reasons are in
[docs/designs/music-mirror/](../../docs/designs/music-mirror/technical.md). This page is the
manual.

| Part | Runs on | When |
|---|---|---|
| `tools/music_mirror.py`, copied to `/opt/muma-mirror/bin/` | mirror NAS, as `muma-mirror` | 01:30, from `/etc/cron.d/muma-mirror` |
| `tools/music_mirror_check.py` | production, `muma-music-mirror-check.timer` | 09:42 |
| `GET /health/music-mirror` | production, music-manager | on request |

## Install

Do these steps in this order. Each install step shows its changes and waits for you to type `yes`.

1. On the mirror NAS, make a ZFS dataset for the copy, with compression off (audio does not
   compress).
2. On the mirror NAS, as root, from a checkout of this repository:

   ```
   scripts/music-mirror/install.sh mirror --source muma-mirror@<library NAS> \
       --dataset <pool>/<dataset> --expected-dirs EPs,Soundcloud,Youtube,artists
   ```

   This step makes the `muma-mirror` account, its two keys and the cron entry. It also pins the
   library NAS's host key, so compare the fingerprint it prints with that NAS.
3. Copy the two public keys (`/opt/muma-mirror/keys/muma-mirror-{read,status}.pub`) to the
   library NAS.
4. On the library NAS, as root:

   ```
   scripts/music-mirror/install.sh library --library <library dataset mount> \
       --status-dir <HOST_BACKUP_PATH>/music-mirror --from <mirror NAS address> \
       --read-key muma-mirror-read.pub --status-key muma-mirror-status.pub
   ```

   The read key can only run `rrsync -ro` on the library. The status key can only write into the
   status directory. Both work only from the mirror NAS's address. The status directory must be
   the directory that production mounts as `/backups`, plus `music-mirror`.
5. On the mirror NAS, fill `MIRROR_NTFY_URL`, `MIRROR_NTFY_TOPIC` and, if the server needs one,
   `MIRROR_NTFY_TOKEN` in `/opt/muma-mirror/env`. Use the alerts topic.
6. On production, set `MIRROR_STATUS_PATH=/backups/music-mirror` in the `.env` and deploy. Then
   run `scripts/backup/install-systemd.sh` again: it installs the check timer when that variable
   is set.
7. Add an Uptime Kuma monitor on `https://<domain>/health/music-mirror`.
8. Start the first copy on a weekend and watch it. It takes about 28 hours at 510 Mbit/s:

   ```
   sudo -u muma-mirror /opt/muma-mirror/bin/music_mirror.py --initial
   ```

9. Do the restore drill in the design: restore one release folder to a scratch directory and
   compare the checksums.

## When It Alerts

| Status | What it means | What you do |
|---|---|---|
| `refused`, fewer files | The library lists fewer than 90% of the files of the last good run. | Find out why the library shrank. Do not override this until you know. |
| `refused`, too much changes | More than 5% of the files or 200 GB would be copied. | If a mass retag or a folder move explains it, run once with `--allow-large-change`. |
| `failed` | rsync, SSH or ZFS failed. The reason names the step. | Read `/opt/muma-mirror/state/run.log` on the mirror NAS. |
| `stale` | No good run in 36 hours. | Check that the mirror NAS is on and that cron ran. |
| `differing` | A copied file has another checksum than the library's. | The alert names the files. Compare them by hand before you trust either side. |
| `missing`, `unconfigured` | Production cannot see the status file. | Check `MIRROR_STATUS_PATH` and the status directory of step 4. |

Exit codes of the job: 0 ok, 1 failed, 2 refused, 3 another run holds the lock, 4 a bad env file.

## Files Only On The Mirror

The mirror keeps every file the library loses, so it grows. The monthly pass counts them
(`orphans` in `/health/music-mirror`). To remove them, run:

```
sudo -u muma-mirror /opt/muma-mirror/bin/music_mirror.py --prune
```

It takes a snapshot first, so the removed files stay in that snapshot until the retention removes
it. Without the snapshot it removes nothing.

## Restore

See "Restore" in the [technical design](../../docs/designs/music-mirror/technical.md#restore).
Every snapshot is readable at `<mirror dataset mount>/.zfs/snapshot/mirror-<stamp>/`. The file
lists of the last 30 runs are in `/opt/muma-mirror/state/manifests/`.
