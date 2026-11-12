# muma-ro: read-only SSH access for an agent

`muma-ro` lets an agent look at a host without being able to change it. The agent's key gets
`muma-ro` as its forced command, so every SSH connection runs the wrapper, whatever the client asked
for. The wrapper checks the text against the host's policy and runs one fixed argument list without
a shell. Root work goes through a helper that checks the text again. Design, verb table and threat
model: [docs/designs/claude-readonly-access/](../../docs/designs/claude-readonly-access/technical.md),
issue #176.

A person installs it, on each host, with this script. An agent never does.

## What you need

- On the host: root, `python3` 3.9 or later, `sudo`, `sshd`.
- On the client (the machine the agent runs on): one key per host class, made by you.

```bash
ssh-keygen -t ed25519 -N '' -C muma-ro-prod -f ~/.ssh/muma-ro-prod_ed25519
```

Copy `~/.ssh/muma-ro-prod_ed25519.pub` and a checkout of this repository to the host.

## Install on one host

1. Pick the example policy for the host class in `tools/muma_ro/policies/` and copy it. Replace
   the paths, container names, units, datasets and ids with the host's own. Leave out a root you
   do not want the agent to see. The loader refuses `/`, `/etc`, `/root`, `/var/lib/docker`, any
   `.ssh` directory and any env key that names a secret.
2. Do a dry run. It prints every change and changes nothing:

   ```bash
   sudo scripts/muma-ro/install.sh --class prod --key-name workstation \
       --pubkey muma-ro-prod_ed25519.pub --client 192.0.2.10 --policy ./policy.json
   ```

3. Run the same command with `--apply`. It prints the plan again and waits for you to type `yes`.
   The last step is the self-test: every enabled verb once, and a list of commands that must be
   refused. If the self-test fails, the script removes the install again and stops with exit 1.
4. On the client, add the host key to `~/.config/muma-mcp/known_hosts`:

   ```bash
   ssh-keyscan -t ed25519 prod.example.com >> ~/.config/muma-mcp/known_hosts
   ```

   Compare the fingerprint with `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` on the host.
5. Add the host to `~/.config/muma-mcp/env` and restart the MCP server:

   ```
   MUMA_RO_HOSTS=prod=muma-ro@prod.example.com
   ```

6. Check it from the client:

   ```bash
   ssh -i ~/.ssh/muma-ro-prod_ed25519 -o IdentitiesOnly=yes muma-ro@prod.example.com help
   ssh -i ~/.ssh/muma-ro-prod_ed25519 -o IdentitiesOnly=yes muma-ro@prod.example.com 'ls /etc'
   ```

   The first prints the verbs and roots. The second prints `muma-ro: refused: ...` and exits 2.

## What the script changes

| Path | What |
|---|---|
| account `muma-ro` | system account, home `/var/lib/muma-ro`, password locked, in no group |
| `/usr/local/lib/muma-ro/muma-ro.pyz` | the wrapper, one zipapp built from `tools/muma_ro/` |
| `/usr/local/bin/muma-ro` | the forced command |
| `/usr/local/libexec/muma-ro-priv` | the root helper |
| `/etc/muma-ro/policy.json` | the host's policy, root 0644; an existing one stays unless you pass `--policy` |
| `/etc/sudoers.d/muma-ro` | `muma-ro ALL=(root) NOPASSWD: /usr/local/libexec/muma-ro-priv`, checked by `visudo -c` first |
| `/var/lib/muma-ro/.ssh/authorized_keys` | `restrict,from="<client>",command="/usr/local/bin/muma-ro --key <name>" <key>`, owned by root |

If `sshd_config` has an `AllowUsers` or `AllowGroups` line, add `muma-ro` to it yourself.

## The Proxmox node

The `proxmox` class adds `pct exec ID -- COMMAND`. The node runs the container's own `muma-ro`
with `--command`, so install `muma-ro` inside each container you list in `ctids` first, with that
container's own policy. Its audit log is in the container's journal.

## Read the log

Each request is one JSON line in the host's journal, under the tag `muma-ro`. A root command has a
second line from the helper.

```bash
journalctl -t muma-ro --since today
```

## Remove it

```bash
sudo scripts/muma-ro/install.sh --uninstall           # dry run
sudo scripts/muma-ro/install.sh --uninstall --apply   # type yes
```

This removes the key, the sudoers file, the launchers, the zipapp, the policy and the account.
