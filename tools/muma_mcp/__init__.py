"""A read-only MCP server that exposes production to a Claude agent.

Implements docs/superpowers/specs/2026-09-04-prod-readonly-mcp-design.md.

Only ``__main__`` imports the MCP SDK. Everything else here -- config, the SQL
guard, redaction, the HTTP client and the database client -- is plain Python, for
two reasons: ``docker/Dockerfile.tools`` copies this whole directory into the
production tools image, which has no business carrying an agent SDK, and the
logic is worth unit-testing without one installed.
"""
