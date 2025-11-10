# Agent Guidelines

- Keep all code and documentation in English.
- Document new or updated code with docstrings, type hints, or reference documentation as appropriate.
- Run automated checks before completing a task:
  - `pytest` for Python services.
  - `npm run test` for frontend changes.
  - `docker compose build` to confirm container images still build.
- Prefer updating existing documentation when behavior changes and add new docs when needed.
- When introducing configuration or environment variables, record them in the README or relevant docs.
- When adding services/modules that appear as separate entries in `docker-compose.yml`, ensure CI/CD builds and publishes a dedicated container image for each service.
- Write concise short documentation for all frontend components.