- **A schema reconcile dry run no longer ends with "schema reconciled".** `--dry-run` changes nothing
  in the database. Its last line said the schema was reconciled anyway, which reads as if the
  statements above it had run. It now says `dry run, schema not changed`.
