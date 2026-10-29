## What and why

<!-- What changes, and what problem it solves. The diff already says what the
     code does; this is for the reasoning behind it. -->

## How it was verified

<!-- Which of these you ran, and anything you checked by hand. CI runs all of
     them, but a red pipeline after review is wasted time on both sides. -->

- `./scripts/lint.sh`
- `./scripts/test/music-management-unit.sh`
- `./scripts/typecheck.sh`
- `./scripts/test/db-integration.sh` (if the change touches SQL or the schema)
- `./scripts/test/frontend-unit.sh` (if the change touches `services/frontend`)

## Checklist

<!-- Delete what does not apply, rather than leaving it unticked. -->

- [ ] New or changed behaviour has a test that fails without the change
- [ ] A new endpoint that reads the database is in `tests/integration/test_router_sql.py`
- [ ] A schema change is in `services/common/schema_tables.py`; a drop, rename or type
      change has a script in `tools/` and is listed in `tests/integration/test_schema_snapshot.py`
- [ ] A new dependency is pinned with `~=` in the requirements file that owns it
- [ ] Nothing secret is in the diff; new configuration is in `.env.example`

## Anything the reviewer should look at first

<!-- The part you are least sure about, or a decision worth a second opinion. -->
