- **The `__TODO` label repair answered 500 on production.** The music-manager image did not
  contain `services/importer`, whose label resolver the repair reuses. It is copied now, and a CI
  test fails whenever code in the container imports a package the image does not carry. See bug
  report 092.
