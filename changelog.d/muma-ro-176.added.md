- **An agent can look at the homelab hosts over SSH without being able to change them.** The new
  `muma-ro` wrapper (`tools/muma_ro/`) is the forced command of the agent's key on each host. It
  checks the text against the host's policy and runs one fixed argument list without a shell:
  `ls`, `find`, `head` of an `.nfo`, `docker logs`, `journalctl`, `zfs list`, `pct config` and
  the other verbs of the design's table. A root command goes through a helper that checks the
  text again. Every request is one line in the host's journal. The MCP server has tools for it
  (`host_ls`, `host_container_logs`, `nas_snapshots`, `pve_relay` and others), plus GET-only
  tools for Portainer, GitLab and the Proxmox API with read-only tokens. Nothing is installed
  yet: a person runs `scripts/muma-ro/install.sh` on each host (issue #176,
  `docs/designs/claude-readonly-access/`).

<!-- release notes -->

- **Alleen-lezen-toegang tot de servers voor een agent.** Een agent kan op een server kijken
  (mappen, logs, schijfruimte, back-ups) zonder iets te kunnen veranderen. Teun installeert het per
  server met een script; tot dan verandert er niets.
