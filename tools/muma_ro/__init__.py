"""``muma-ro``: a read-only command wrapper for an SSH forced command (issue #176).

A host gives the agent's key ``command="/usr/local/bin/muma-ro --key <name>"`` in
``authorized_keys``. sshd then runs this program for every connection, whatever the client
asked for, and passes the client's text in ``SSH_ORIGINAL_COMMAND``. This package parses that
text against the host's policy (``/etc/muma-ro/policy.json``) and runs one fixed argument list
with ``execve``, never through a shell.

Standard library only, Python 3.9 or later: it runs on hosts that have neither this
repository nor its dependencies. ``scripts/muma-ro/install.sh`` builds it into one zipapp.

Design: docs/designs/claude-readonly-access/technical.md.
"""
